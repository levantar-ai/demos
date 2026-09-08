# VHS tape for the post 05 demo video: the customer's identity enforced at
# the gateway by Policy in AgentCore.
#
# The slow terraform reads are done BEFORE the capture, not inside it, or the
# hidden setup can still be on screen when Show fires (see the post 05 video
# fix). Export these first, then record:
#
#   cd agentcore/05-identity
#   export REGION=$(aws-vault exec lev:andy.rea -- terraform -chdir=terraform output -raw aws_region)
#   export INVOKE_URL=$(aws-vault exec lev:andy.rea -- terraform -chdir=terraform output -raw invoke_url)
#   export CLIENT_ID=$(aws-vault exec lev:andy.rea -- terraform -chdir=terraform output -raw customers_client_id)
#   export GATEWAY_URL=<the gateway mcp url from terraform state>
#   export PASSWORD=$(cat /path/to/c-1000.pw)
#   export SESSION=cedar-demo-video-session-00000000000000001
#   vhs demo.tape
#
# The stack must be deployed in ENFORCE mode with customers c-1000 and c-1001
# in the pool. The video shows only the example being exercised.
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
Sleep 3s
Type `export PS1='\[\e[1;36m\]agentcore >\[\e[0m\] '; clear; printf '\033[3J'`
Enter
Sleep 2s
Show

Type "# the runtime checks the customer's token, the agent relays it to the gateway, and a Cedar policy at the gateway enforces the customer on every call"
Enter
Sleep 1.5s

Type "# sign in as Brightwell customer c-1000 and keep the access token"
Enter
Sleep 1s

Type `export TOKEN=$(aws cognito-idp initiate-auth --region "$REGION" --client-id "$CLIENT_ID" --auth-flow USER_PASSWORD_AUTH --auth-parameters USERNAME=c-1000,PASSWORD="$PASSWORD" --query AuthenticationResult.AccessToken --output text)`
Enter
Wait
Sleep 1s

Type "# through the agent, list my orders"
Enter
Sleep 1s

Type `curl -s "$INVOKE_URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $SESSION" -d '{"prompt": "list my orders"}' | jq -c '.result.customer_id, (.result.orders[] | {order_id, total, status})'`
Enter
Wait
Sleep 3s

Type "# the enforcement is at the gateway, not the agent. ask the gateway directly, with my own token, for my own orders"
Enter
Sleep 1s

Type "python3 probe_gateway.py c-1000"
Enter
Wait
Sleep 2.5s

Type "# now ask it, with the same token, for another customer's orders"
Enter
Sleep 1s

Type "python3 probe_gateway.py c-1001"
Enter
Wait
Sleep 5s
