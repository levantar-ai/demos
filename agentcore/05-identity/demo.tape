# VHS tape for the post 05 demo video, an agent that knows who is calling.
#
# The slow work is done BEFORE the capture, not inside it. The four terraform
# reads hit the S3 state backend and are slower than any fixed Sleep, so if
# they run inside the hidden block the capture can start before they finish
# and the setup shows on camera. Export them first, then record:
#
#   cd agentcore/05-identity
#   export REGION=$(aws-vault exec lev:andy.rea -- terraform -chdir=terraform output -raw aws_region)
#   export INVOKE_URL=$(aws-vault exec lev:andy.rea -- terraform -chdir=terraform output -raw invoke_url)
#   export CLIENT_ID=$(aws-vault exec lev:andy.rea -- terraform -chdir=terraform output -raw customers_client_id)
#   export PASSWORD=$(cat /path/to/c-1000.pw)
#   export SESSION=identity-demo-video-session-00000000000000005
#   vhs demo.tape
#
# The stack must be deployed, customer c-1000 in the pool, and an aws-vault
# session warm. The video shows only the example being exercised.
Output demo.mp4
Set Shell "bash"
Set FontSize 20
Set Width 1600
Set Height 900
Set Padding 24
Set TypingSpeed 30ms
Set WaitTimeout 600s
Set Theme {"background":"#0a0a0e","foreground":"#d6dae3","cursor":"#22d3ee","black":"#16161c","red":"#ef4444","green":"#4ade80","yellow":"#fbbf24","blue":"#60a5fa","magenta":"#f472b6","cyan":"#22d3ee","white":"#d1d5db","brightBlack":"#52525e","brightRed":"#f87171","brightGreen":"#86efac","brightYellow":"#fde047","brightBlue":"#93c5fd","brightMagenta":"#f9a8d4","brightCyan":"#67e8f9","brightWhite":"#f4f4f5","selection":"#164e63"}

# Hidden setup. INVOKE_URL, CLIENT_ID, REGION, PASSWORD and SESSION are already
# in the environment (see header), so aws-vault carries them into this shell and
# nothing here waits on the network. Only PS1 and a clear, both instant.
Hide
Type "exec aws-vault exec lev:andy.rea -- bash --norc"
Enter
Sleep 3s
Type `export PS1='\[\e[1;36m\]agentcore >\[\e[0m\] '; clear; printf '\033[3J'`
Enter
Sleep 2s
Show

Type "# an agent that knows who is calling. the runtime checks the customer's token before the agent ever sees the request"
Enter
Sleep 1.5s

Type "# sign in as Brightwell customer c-1000 and keep the access token"
Enter
Sleep 1s

Type `TOKEN=$(aws cognito-idp initiate-auth --region "$REGION" --client-id "$CLIENT_ID" --auth-flow USER_PASSWORD_AUTH --auth-parameters USERNAME=c-1000,PASSWORD="$PASSWORD" --query AuthenticationResult.AccessToken --output text)`
Enter
Wait
Sleep 1s

Type "# the token says who is asking. the request body no longer does"
Enter
Sleep 1s

Type `curl -s "$INVOKE_URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $SESSION" -d '{"prompt": "list my orders"}' | jq -c '.result.customer_id, (.result.orders[] | {order_id, placed_at, total, status})'`
Enter
Wait
Sleep 3s

Type "# an order on someone else's account is not found, rather than looked up"
Enter
Sleep 1s

Type `curl -s "$INVOKE_URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $SESSION" -d '{"prompt": "where is order 1014?"}' | jq`
Enter
Wait
Sleep 2.5s

Type "# and without a token the request never reaches the agent"
Enter
Sleep 1s

Type `curl -si "$INVOKE_URL" -H "Content-Type: application/json" -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $SESSION" -d '{"prompt": "list my orders"}' | sed -n '1p;$p'; echo`
Enter
Wait
Sleep 5s
