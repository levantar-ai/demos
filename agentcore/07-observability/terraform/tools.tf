# The sandbox the agent runs untrusted analysis code in. SANDBOX network
# mode means the sandbox has no network access at all, so code executed
# there cannot reach the internet or anything in the account.

resource "aws_bedrockagentcore_code_interpreter" "sandbox" {
  name        = local.interpreter_name
  description = "Sandboxed pandas analysis for the demos series"

  network_configuration {
    network_mode = "SANDBOX"
  }

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}
