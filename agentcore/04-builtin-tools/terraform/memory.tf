# The memory store and the long-term extraction strategy.
#
# Events (raw conversation turns) live for event_expiry_duration days and
# are the short-term memory. The USER_PREFERENCE strategy watches those
# events and asynchronously extracts preference records into the
# /users/{actorId} namespace, which is the long-term memory the agent
# queries across sessions.

resource "aws_bedrockagentcore_memory" "agent" {
  name                  = local.memory_name
  event_expiry_duration = 7

  tags = {
    Project = "demos"
    Demo    = local.demo_slug
  }
}

resource "aws_bedrockagentcore_memory_strategy" "preferences" {
  memory_id  = aws_bedrockagentcore_memory.agent.id
  name       = "UserPreferences"
  type       = "USER_PREFERENCE"
  namespaces = ["/users/{actorId}"]
}
