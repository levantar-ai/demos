# VHS tape for the post 04 demo video, running pandas in a sandbox.
# Prereqs (off-camera): stack deployed, aws-vault session warm. Record with:
#   vhs demo.tape
# The video shows only the example being exercised. Provisioning is the
# post's job, not the video's, same as post 03.
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
Type `unset PROMPT_COMMAND; export PS1='\[\e[1;36m\]agentcore >\[\e[0m\] ' && export ARN=$(terraform -chdir=terraform output -raw runtime_arn) && clear`
Enter
Sleep 3s
Type "clear"
Enter
Sleep 1s

Show

Type "# an agent that runs pandas in a sandbox, no internet and no credentials in there"
Enter
Sleep 1.5s

Type "# a CSV, eight of Brightwell's orders. the point is where the code runs, not what it computes"
Enter
Sleep 1s

Type `python3 -c 'import json; print(json.load(open("payload.json"))["csv"])'`
Enter
Sleep 3s

Type "# the agent writes it into a sandbox session, runs pandas there, reads the result back"
Enter
Sleep 1s

Type `aws bedrock-agentcore invoke-agent-runtime --cli-binary-format raw-in-base64-out --agent-runtime-arn "$ARN" --runtime-session-id demo-video-session-000000000000000004 --payload file://payload.json --region us-east-1 /dev/stdout | python3 -c 'import sys,json; print(json.JSONDecoder().raw_decode(sys.stdin.read())[0]["result"])'`
Enter
Wait
Sleep 5s
