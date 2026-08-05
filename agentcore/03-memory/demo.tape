# VHS tape for the post 03 demo video: memory events + cross-session recall.
# Prereqs (off-camera): stack deployed, extraction already run for the actor
# so recall returns records immediately, aws-vault session warm. Record with:
#   vhs demo.tape
Output demo.mp4
Set Shell "bash"
Set FontSize 20
Set Width 1600
Set Height 900
Set Padding 24
Set TypingSpeed 30ms
Set WaitTimeout 240s
Set Theme {"background":"#0a0a0e","foreground":"#d6dae3","cursor":"#22d3ee","black":"#16161c","red":"#ef4444","green":"#4ade80","yellow":"#fbbf24","blue":"#60a5fa","magenta":"#f472b6","cyan":"#22d3ee","white":"#d1d5db","brightBlack":"#52525e","brightRed":"#f87171","brightGreen":"#86efac","brightYellow":"#fde047","brightBlue":"#93c5fd","brightMagenta":"#f9a8d4","brightCyan":"#67e8f9","brightWhite":"#f4f4f5","selection":"#164e63"}

Hide
Type "exec aws-vault exec lev:andy.rea -- bash --norc"
Enter
Sleep 2s
Type `unset PROMPT_COMMAND; cd /home/andy-rea/development/demos/agentcore/03-memory && export PS1='\[\e[1;36m\]agentcore >\[\e[0m\] ' && export ARN=$(terraform -chdir=terraform output -raw runtime_arn) MEMORY_ID=$(terraform -chdir=terraform output -raw memory_id) && clear`
Enter
Type `ACCT=$(aws sts get-caller-identity --query Account --output text); redact() { sed -u "s/$ACCT/<ACCOUNT-ID>/g"; }`
Enter
Sleep 3s

Sleep 10s
Type "clear"
Enter
Sleep 1s
Type "clear"
Enter
Sleep 1s

Show

Type "# an agent that remembers, with AgentCore Memory — store a preference in session A"
Enter
Sleep 1.5s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$ARN" --runtime-session-id memory-video-session-a-00000000000001 --payload '{"actor": "andy", "session": "session-a", "prompt": "remember: my name is Andy and I always prefer DPD for deliveries"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 2s

Type "# short-term memory — the agent reads its own session events back with recap"
Enter
Sleep 1s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$ARN" --runtime-session-id memory-video-session-a-00000000000001 --payload '{"actor": "andy", "session": "session-a", "prompt": "recap"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 3s

Type "# long-term — extraction runs async server-side; ask from a DIFFERENT session"
Enter
Sleep 1s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$ARN" --runtime-session-id memory-video-session-b-00000000000002 --payload '{"actor": "andy", "session": "session-b", "prompt": "which delivery carrier do I prefer?"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 5s
