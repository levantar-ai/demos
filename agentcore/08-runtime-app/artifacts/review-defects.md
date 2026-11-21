# defects pass, gpt-5.6-sol

### 1. Major — A live customer bearer token is still placed in Cognito `ClientMetadata`

**File and quote**

`agentcore/08-runtime-app/exchange/handler.py`:

> `ClientMetadata={"subject_token": subject_token, "grant": TOKEN_EXCHANGE_GRANT},`

The adjacent comment confirms:

> “Cognito's API reference says not to send sensitive information in ClientMetadata”

**Why it is wrong**

`subject_token` is an active customer credential. Cognito explicitly says `ClientMetadata` is not a secure channel and must not contain sensitive information. The token is duplicated there so the pre-token-generation trigger can read it. Calling this a teaching compromise does not remove the credential exposure from an independently deployable stack.

**Fix**

Pass only a random, short-lived, single-use handle in `ClientMetadata`. Store the verified claims or token in an encrypted record bound to the app client, service user and grant; have the pre-token trigger atomically consume it. Prefer a managed identity provider with native RFC 8693 support. Until changed, prominently state that the exchange must not process real customer credentials.

---

### 2. Major — Recreating a Cognito username grants access to the previous customer’s orders

**Files and quotes**

`agentcore/08-runtime-app/exchange/triggers.py`:

> `"customer_id": claims["username"],`  
> `"customer_sub": claims["sub"],`

`agentcore/08-runtime-app/terraform/policy.tf`:

> `principal.getTag("customer_id") == context.input.customer_id`

`agentcore/08-runtime-app/tool/orders.py`:

> `if r["customer_id"] == customer_id`

`agentcore/08-runtime-app/agent/main.py` acknowledges the underlying condition:

> “an administrator can delete a username and create it again for someone else”

**Why it is wrong**

Memory uses the immutable Cognito `sub`, but order authorization uses the reusable username. If `c-1000` is deleted and recreated, the replacement identity receives `customer_id=c-1000`; Cedar permits the request and the tool returns the original customer’s rows. The otherwise unused `customer_sub` claim does not prevent this.

**Fix**

Map the verified Cognito `sub` to an immutable Brightwell customer identifier and use that identifier end-to-end: exchanged-token claim, Cedar comparison and order-data lookup. Do not derive order authorization from `username`. Add a regression test that deletes/recreates a username and verifies that the new subject cannot access the old account.

---

### 3. Major — The 30-second body deadline resets for every ASGI body chunk

**Files and quotes**

`agentcore/08-runtime-app/POST.md`:

> “a 2 MB body that arrives within 30 seconds”

`agentcore/08-runtime-app/agent/main.py`:

> `return await asyncio.wait_for(receive(), BODY_READ_SECONDS)`

and:

> “each read of the body given BODY_READ_SECONDS”

**Why it is wrong**

The implementation gives every call to `receive()` a fresh 30 seconds; it does not require the complete body to arrive within 30 seconds. A fixed-length request can be fragmented and deliver another chunk just before each timeout, holding one of the eight admission slots indefinitely. Rejecting `Transfer-Encoding` does not prevent fragmentation of a `Content-Length` body. The existing stalled-body test only covers a request that sends no further data.

**Fix**

Create one deadline when the wrapper is constructed and use the remaining time for every read:

```python
def timely(receive):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + BODY_READ_SECONDS

    async def read():
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise HTTPException(408, "request body timed out")
        try:
            return await asyncio.wait_for(receive(), remaining)
        except asyncio.TimeoutError:
            raise HTTPException(408, "request body timed out") from None

    return read
```

Add a test that sends several chunks, each less than the per-read timeout apart, but whose total duration exceeds the overall deadline.

not ready
