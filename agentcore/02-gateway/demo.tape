# VHS tape for the post 02 demo video: gateway + tool Lambda + agent.
# Prereqs (off-camera): backend init done, ECR repo exists, image pushed
# with TAG, aws-vault session warm. Record with:
#   TAG=<git sha> vhs demo.tape
Output demo.mp4
Set Shell "bash"
Set FontSize 20
Set Width 1600
Set Height 900
Set Padding 24
Set TypingSpeed 30ms
Set WaitTimeout 600s
Set Theme {"background":"#0a0a0e","foreground":"#d6dae3","cursor":"#22d3ee","black":"#16161c","red":"#ef4444","green":"#4ade80","yellow":"#fbbf24","blue":"#60a5fa","magenta":"#f472b6","cyan":"#22d3ee","white":"#d1d5db","brightBlack":"#52525e","brightRed":"#f87171","brightGreen":"#86efac","brightYellow":"#fde047","brightBlue":"#93c5fd","brightMagenta":"#f9a8d4","brightCyan":"#67e8f9","brightWhite":"#f4f4f5","selection":"#164e63"}

Hide
Type "exec aws-vault exec lev:andy.rea -- bash --norc"
Enter
Sleep 2s
Type `unset PROMPT_COMMAND; cd /home/andy-rea/development/demos/agentcore/02-gateway && export PS1='\[\e[1;36m\]agentcore >\[\e[0m\] ' && clear`
Enter
Type `ACCT=$(aws sts get-caller-identity --query Account --output text); redact() { sed -u "s/$ACCT/<ACCOUNT-ID>/g"; }`
Enter
Sleep 3s
# Client id and secret are read off camera so they never appear on screen.
# Only the resulting short-lived token is used, and only its prefix shown.
Type `TOKEN_URL="https://demos-agentcore-02-gateway-$ACCT.auth.us-east-1.amazoncognito.com/oauth2/token"`
Enter
Sleep 1s

Type "clear"
Enter
Sleep 1s

Show

Type "# a Lambda as an MCP tool behind AgentCore Gateway — Cognito JWT on every call"
Enter
Sleep 1.5s

Type "ls agent/ tool/ terraform/"
Enter
Sleep 2.5s

Type "# nothing deployed yet — build the lot from scratch"
Enter
Sleep 1.5s

Type "terraform -chdir=terraform apply -auto-approve -var image_tag=$TAG 2>&1 | redact"
Enter
Wait
Sleep 3s

Type "# cognito pool, gateway, target, lambda and runtime are live — ask about an order"
Enter
Sleep 1s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$(terraform -chdir=terraform output -raw runtime_arn)" --runtime-session-id demo-video-session-000000000000000002 --payload '{"prompt": "where is order 42?"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 2s

Type "# a distracting number in the prompt — still resolves order 42"
Enter
Sleep 1s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$(terraform -chdir=terraform output -raw runtime_arn)" --runtime-session-id demo-video-session-000000000000000002 --payload '{"prompt": "in 2 days, where is order 42?"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 2s

Type "# an order the tool does not know"
Enter
Sleep 1s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$(terraform -chdir=terraform output -raw runtime_arn)" --runtime-session-id demo-video-session-000000000000000002 --payload '{"prompt": "is order 99 ok?"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 2s

Type "# now the same call with a client-credentials token from Cognito"
Enter
Sleep 1s

Type `CREDS=$(aws secretsmanager get-secret-value --secret-id demos-agentcore-02-gateway-agent-client --query SecretString --output text --region us-east-1)`
Enter
Wait
Sleep 1s

Type `TOKEN=$(curl -s -u "$(jq -r .client_id <<<"$CREDS"):$(jq -r .client_secret <<<"$CREDS")" -d "grant_type=client_credentials&scope=orders-api/invoke" "$TOKEN_URL" | jq -r .access_token)`
Enter
Wait
Sleep 1s

Type `echo "${TOKEN:0:18}... ($(printf %s "$TOKEN" | wc -c) chars)"`
Enter
Wait
Sleep 2s

Type `curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$(terraform -chdir=terraform output -raw gateway_url)" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"orders___lookup_order","arguments":{"order_id":"42"}}}'`
Enter
Wait
Sleep 3s

Type "# no token, no entry — and this is the call that would hit the Lambda"
Enter
Sleep 1s

Type `curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$(terraform -chdir=terraform output -raw gateway_url)" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"orders___lookup_order","arguments":{"order_id":"42"}}}'`
Enter
Wait
Sleep 4s
