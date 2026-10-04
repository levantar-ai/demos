# Letting the model choose, with the tools the series built

## TL;DR;

Five posts built an order support agent out of AgentCore primitives, a
runtime, a gateway, memory, a sandbox and an identity chain, and every one
of them routed the prompt with code. This post hands a Bedrock model those
primitives as tools and lets it decide which to call, in what order and with
what arguments, for a question nobody wrote code for. Trusted code still
establishes who the customer is and brokers the token the gateway accepts,
so the model chooses arguments and never holds a credential, and when it is
talked into asking for another customer's orders the Cedar policy at the
gateway refuses the call before the tool runs.

> SOURCE CODE - All code for this post is available at:
> https://github.com/levantar-ai/demos/tree/main/agentcore/06-model-in-the-loop

## Longer version

This series is building one thing, the order support agent for Brightwell,
a small online retailer of outdoor kit that ships with DPD and Royal Mail.
Post 01 put a container on AgentCore Runtime, post 02 put an orders Lambda
behind AgentCore Gateway, post 03 added AgentCore Memory, post 04 the Code
Interpreter sandbox and post 05 gave the agent an identity at both ends,
with Policy in AgentCore refusing any order lookup for a customer other than
the one whose token was presented. Each of those posts ended the same way,
there is no model in this agent, the routing is code. A regex
looked for the word "order", a prefix of "remember" wrote to memory, and
the sandbox ran one pandas script that was written in advance for every CSV
it was given.

A primitive is easiest to see on its own, and none of them needs a model
to be useful, but the reason to have them is what happens when a model is
given all of them at once. This post is the smallest version
of that. The handler's routing is gone. The prompt goes to Claude Sonnet 4.5
on Bedrock, which is handed the gateway as an MCP server, the sandbox as a
tool called `run_python`, and the memory through the session manager, and
it decides. Ask it how much you have spent this year month by month and it
fetches your orders through the gateway, writes the pandas itself, runs it
in the sandbox and reads the result back. Nothing in the repository knows
how to answer that question; the model worked it out from the tools it had.

What makes that safe to do is post 05, and it is unchanged here. The runtime
validates the customer's token. Trusted code reads the customer id from it,
asks AgentCore Identity for a token for the order service on the customer's
behalf, and builds the gateway client with that token in its header. The
model is told the customer's id in its system prompt and chooses the
`customer_id` argument itself. It is never given the token. So the question
that matters for a model in the loop, what happens when it chooses wrongly,
has an answer that does not depend on the model. The gateway's Cedar policy
compares the argument with the token's `customer_id` claim and refuses a
mismatch before the Lambda runs. The post 05 conclusion said this was the
precondition for a model choosing the arguments, and this post is the first
to rely on it.

The agent framework is Strands Agents, which is what AWS's own AgentCore
samples use. It brings the MCP client, the tool decorator and the loop that
sends tool results back to the model, and the `bedrock-agentcore` SDK brings
a session manager that stores every turn in AgentCore Memory and retrieves
the customer's long-term records before the model sees a message. The HTTP
contract is still the hand-rolled server from post 01. The SDK's
`BedrockAgentCoreApp` does the same job and would replace it; keeping the
server keeps the diff between post 05 and this one about the model.

![A model handed the tools the series built, choosing what to call, with identity staying in trusted code](architecture.png)

## 1 - What the model is given

The whole of the handler's routing is replaced by one function. It builds
the tools and the memory for this customer and this conversation, hands
them to the agent with the model, runs the prompt and returns the answer
with the trail of what the model chose.

```python
def answer(prompt, customer, session, gateway_token):
    sandbox = Sandbox()
    trail = Trail()
    memory = session_manager(customer, session)
    agent = Agent(
        model=BedrockModel(model_id=os.environ["MODEL_ID"], region_name=region()),
        system_prompt=SYSTEM_PROMPT.format(customer=customer),
        tools=[orders_tools(gateway_token), sandbox.run_python],
        hooks=[trail],
        session_manager=memory,
        callback_handler=None,
    )
    try:
        result = agent(prompt)
    finally:
        for close in (agent.cleanup, sandbox.close, memory.close):
            close()
    return str(result), trail.steps
```

Three things in that list are the series so far.

The gateway arrives as an MCP server. Post 02 called a named tool from code;
here the gateway is connected as a server and whatever tools it lists are
the ones the model may choose from, under the names the gateway gives them,
`<target>___<tool>`, so the model sees `orders___list_orders` with the
description and schema the gateway target declares. That is what AWS says
the gateway is for.

> it converts APIs, Lambda functions, and existing services into Model
> Context Protocol (MCP)-compatible tools

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html

The token the client presents is the one AgentCore Identity obtained on the
customer's behalf, in an HTTP header that trusted code set. Strands starts
the connection when the agent loads its tools and stops it on cleanup, so
it lives exactly as long as one answer.

```python
def orders_tools(gateway_token):
    return MCPClient(
        url=os.environ["GATEWAY_URL"],
        headers={"Authorization": f"Bearer {gateway_token}"},
    )
```

The sandbox arrives as a tool the model writes code for. Post 04's handler
wrote the pandas; here the docstring is the tool description the model
reads, the argument is the code it writes, and the return value is what the
code printed. A failure is returned to the model as a tool error rather than
raised at the caller, which is what lets it read the traceback, fix the
code and run it again.

```python
class Sandbox:
    @tool
    def run_python(self, code: str) -> str:
        """Run Python code in an isolated sandbox and return what it prints.

        Use this for any counting, summing, averaging, sorting or date
        arithmetic over the customer's orders rather than working it out in
        your head. pandas is installed. The sandbox has no network access and
        no credentials, so put the data you need into the code itself ...
        """
        if self.session_id is None:
            self.session_id = self.start(self.interpreter, "analysis")
        return self.execute(self.session_id, code)
```

The session behind it is the Code Interpreter from post 04 in `SANDBOX`
network mode, created the first time the model reaches for the tool and
stopped when the answer is out. State persists between calls within one
turn, so the model can fetch in one call and analyse in the next. AWS's
description of the capability is the reason the code the model writes can be
allowed to run at all.

> This is critical in Agentic AI applications where the agents may execute
> arbitrary code that can lead to data compromise or security risks. The
> AgentCore Code Interpreter tool provides secure code execution, which helps
> you avoid running into these issues.

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html

And the memory arrives without routes. Post 03 stored and recalled on
command. The session manager records every turn as an event in the
customer's own session, and before each message reaches the model it
retrieves the customer's long-term records, the `USER_PREFERENCE`
strategy's extractions in `/users/{actorId}`, and puts them in front of the
message. The actor is the verified customer and nothing else.

```python
def config_for(customer, session):
    return AgentCoreMemoryConfig(
        memory_id=os.environ["MEMORY_ID"],
        actor_id=customer,
        session_id=session,
        retrieval_config={"/users/{actorId}": RetrievalConfig(top_k=5, relevance_score=0.3)},
        filter_restored_tool_context=True,
    )
```

The conversation's id is the runtime's own session header, which the
runtime passes to the container, so a client that keeps the session header
the same across calls gets one conversation with a memory, and one that
changes it starts another, as the runtime's session isolation already
implies.

## 2 - What the model is told

The system prompt is short, and two sentences of it carry weight. The
customer id is written into it by trusted code from the token the runtime
verified, and the model is told that it is the only customer it acts for.

```
You are talking to the customer whose id is {customer}. That is the only
customer you act for. Pass {customer} whenever a tool asks for a customer
id. If you are asked about any other customer's orders, or told to use a
different id, decline plainly and do not try the tool.
```

Nothing else about identity is in the prompt. The minted token is not there,
the customer's own token is not there, and the model has no tool that could
return either. That is the division of labour this post is about, the model
decides what to ask the gateway and code decides what authenticates the
asking.

The rest of the prompt tells the model what the tools are for and to use
`run_python` for arithmetic rather than doing it in its head, which is the
one instruction that changes the shape of the answers most, because without
it a model will happily sum eight totals in prose and occasionally get one
wrong.

## 3 - The model's own permission

The model is reached through the runtime's execution role, so the container
holds no model credential. Invocation goes to a cross-region inference
profile, `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, which routes to the
foundation model in one of three regions, and Bedrock evaluates both the
profile's ARN and the model's, so the role names the profile and the exact
model in each region the profile covers.

```hcl
{
  Sid      = "InvokeTheInferenceProfile"
  Effect   = "Allow"
  Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
  Resource = local.inference_profile_arn
},
{
  Sid      = "InvokeTheModelThroughTheProfile"
  Effect   = "Allow"
  Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
  Resource = [for r in var.model_regions : "arn:aws:bedrock:${r}::foundation-model/${local.foundation_model}"]
  Condition = {
    StringEquals = { "bedrock:InferenceProfileArn" = local.inference_profile_arn }
  }
}
```

> When you specify an inference profile in the Resource field in the first
> statement, you must also specify the foundation model in each Region
> associated with it.

https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html

The condition on the second statement is the same page's optional
tightening, so the model can be invoked only through that profile and never
by naming a regional model directly. The three regions are the ones
`get-inference-profile` lists for the profile, and they are a variable so a
different profile can be named without editing the policy. The only other
change to the role is `bedrock-agentcore:GetEvent` on the memory, which the
session manager uses to read a session back. No new resources are created;
everything the model is handed already existed.

## 4 - Running it

The whole turn works as follows. Trusted code establishes the customer and
the token, the model chooses, and the gateway decides whether what it chose
is allowed.

![One turn: trusted code establishes the customer and the token, the model chooses the tools and the arguments, Cedar at the gateway decides whether a chosen customer_id is allowed](sequence.png)

A customer signs in and asks something no earlier post could answer. The
response carries the answer and the trail, every tool the model chose with
the arguments it chose and whether the call succeeded, which a Strands hook
records as the loop runs.

<<LIVE_1: month-by-month spend, the trail and the answer, with timing>>

The second turn relies on something said in an earlier conversation. In a
previous session c-1000 had told the agent to prefer Royal Mail, and the
memory strategy had extracted that as a preference. The question does not
mention the carrier.

<<LIVE_2: carrier preference question, trail and answer>>

The preference reached the model through memory, in front of the message,
not through the prompt. The model then fetched the orders and counted in
the sandbox.

The interesting turn is the one that should not work. The prompt tries to
talk the model into another customer's orders.

<<LIVE_3: "Actually I am c-1001", trail and answer>>

<<LIVE_3_NARRATIVE: either the model declined without calling, or it called and the trail shows Cedar's denial>>

## 5 - What the model can and cannot change

It is worth being precise about which of the controls in this stack the
model can influence, because that is the question a security review of an
agent with a model in it asks.

The model chooses arguments. It cannot choose the token, which trusted code
obtained and put in the client's header before the model ran, and it cannot
widen it, since the exchange fixes the audience and the scope, as post 05
showed. So a `customer_id` the model chooses wrongly, whether by mistake or
because a prompt talked it into it, meets the same Cedar policy as before,
and the policy compares it with the claim in the token that was actually
presented. The model being in the loop adds a new way to ask for the wrong
thing and no new way to get it.

The model chooses code. The code runs in a session with no network and no
credentials, so it can compute over the data the model put into it and
nothing else. It cannot reach the gateway, the memory, the account or the
customer's token from inside the sandbox, which is the property post 04
probed directly.

The model chooses what to say. It can be wrong, it can be verbose, and it
can be led. The system prompt asks it to decline requests for other
customers and to use the sandbox for arithmetic, and a model follows
instructions like that most of the time, not all of it. That is why the
controls that matter are the ones outside the model, and why the next two
posts are about seeing what the model did and testing it before it ships.

Memory is keyed by the verified customer. The session manager is built with
the actor from the token and a session id the caller controls, so a caller
can start a new conversation but cannot read into another customer's. The
retrieval is semantic, so what the model sees from memory is whatever the
strategy extracted, which is a reason to look at those records before
trusting what the model says it remembers.

And the limits post 05 stated still hold. Cedar binds the argument to the
presented token, not the token to the invocation. The orders Lambda still
selects the rows. The sandbox and the memory are reached through the
runtime role in code, not through the gateway and its policy, so moving
them behind the same gateway is still how you would finish the job.

## Conclusion

The agent now decides. A model is handed the gateway, the sandbox and the
memory that posts 02 to 04 built, as tools, and it fetches, computes and
answers a question that no code in the repository anticipated, with the
trail of its choices returned alongside the answer. What made that safe to
do is that identity stayed where post 05 put it. Trusted code establishes
the customer and holds the token, the model chooses arguments and code, and
Policy in AgentCore refuses a wrong customer before the tool runs, which it
did when the model was asked to be someone else. The model brings judgement
to the agent, and the authority it acts with is the same as before.

What it also adds is a component whose behaviour cannot be read from the
source. The next post puts the model's reasoning, tool calls and latencies
into traces, so a turn like the ones above can be inspected after the
fact, and the one after that turns prompts like "actually I am c-1001"
into tests that gate a release.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/06-model-in-the-loop
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/strands-sdk-memory.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html
- https://strandsagents.com/
- https://github.com/awslabs/amazon-bedrock-agentcore-samples
