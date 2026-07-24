# VHS tape for the post 01 demo video: real terraform apply + invocations.
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
Set WaitTimeout 180s
Set Theme {"background":"#0a0a0e","foreground":"#d6dae3","cursor":"#22d3ee","black":"#16161c","red":"#ef4444","green":"#4ade80","yellow":"#fbbf24","blue":"#60a5fa","magenta":"#f472b6","cyan":"#22d3ee","white":"#d1d5db","brightBlack":"#52525e","brightRed":"#f87171","brightGreen":"#86efac","brightYellow":"#fde047","brightBlue":"#93c5fd","brightMagenta":"#f9a8d4","brightCyan":"#67e8f9","brightWhite":"#f4f4f5","selection":"#164e63"}

Hide
Type "exec aws-vault exec lev:andy.rea -- bash --norc"
Enter
Sleep 2s
Type "unset PROMPT_COMMAND; cd /home/andy-rea/development/demos/agentcore/01-first-agent && export PS1='\[\e[1;36m\]agentcore >\[\e[0m\] ' && clear"
Enter
Show

Type "# a first agent on AgentCore Runtime — 40 lines of stdlib Python, 5 terraform resources"
Enter
Sleep 1.5s

Type "ls agent/ terraform/"
Enter
Sleep 2.5s

Type "terraform -chdir=terraform apply -auto-approve -var image_tag=$TAG"
Enter
Wait
Sleep 2s

Type "# it's live — ask it something"
Enter
Sleep 1s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$(terraform -chdir=terraform output -raw runtime_arn)" --runtime-session-id demo-video-session-000000000000000001 --payload '{"prompt": "hello agentcore"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 2s

Type "# same session again — the microVM is warm now"
Enter
Sleep 1s

Type `time aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$(terraform -chdir=terraform output -raw runtime_arn)" --runtime-session-id demo-video-session-000000000000000001 --payload '{"prompt": "still there?"}' --region us-east-1 /dev/stdout`
Enter
Wait
Sleep 4s
