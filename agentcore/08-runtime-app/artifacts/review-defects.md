# defects pass, gpt-5.6-sol

### 1. Major — The post misstates what the external Runtime client receives on application errors

**Files and quotes**

- `agentcore/08-runtime-app/POST.md`:
  > “An exception that escapes the function is answered by the SDK with a 500 whose body is the exception's message”
- `agentcore/08-runtime-app/LINKEDIN-POST.md`:
  > “an exception that escapes your function goes back to the client with its message”
- `agentcore/08-runtime-app/POST.md`:
  > “The other is what a client is told when a turn fails.”

**Why it is wrong**

That describes a client calling the SDK’s Starlette application directly, not a caller invoking it through AgentCore Runtime. Runtime translates non-2xx responses from the container into its external `RuntimeClientError`/424 response rather than transparently forwarding the container’s status and JSON body.

The repository itself documents this distinction for 4xx responses:

- `agentcore/08-runtime-app/README.md`:
  > “A 4xx from the container reaches the client as the runtime's 424, `Received error (400) from runtime`”

The deployment artifacts only demonstrate this 400 behavior; they do not demonstrate an escaped exception or show its message reaching an external Runtime client. Likewise, returning the generic application 502 does not mean the external caller receives that 502 and `{"error":"request failed"}` unchanged.

Catching exceptions is still sensible for controlled logging, direct deployment, and avoiding details in the container response, but the stated deployed-client behavior and evidence are incorrect.

**Fix**

Distinguish the two interfaces explicitly:

- Direct call to `BedrockAgentCoreApp`: the SDK’s 500 body can contain the exception text.
- Call through AgentCore Runtime: Runtime converts the container error into its service-level error response.

Update the post and LinkedIn claim accordingly, and add a deployed escaped-exception probe to `artifacts/README.md` if making any claim about the exact external response.

---

### 2. Major — A customer bearer token is placed in Cognito `ClientMetadata`

**File and quote**

- `agentcore/08-runtime-app/exchange/handler.py`:
  > `ClientMetadata={"subject_token": subject_token, "grant": TOKEN_EXCHANGE_GRANT},`
- The adjacent comment acknowledges:
  > “Cognito's API reference says not to send sensitive information in ClientMetadata”

**Why it is wrong**

The subject token is a live customer bearer credential. Cognito explicitly warns that `ClientMetadata` is not encrypted, validated, or stored as a secure secret channel and must not contain sensitive information. The implementation duplicates the full bearer token into that field so the pre-token-generation trigger can consume it.

Calling this a teaching compromise in a source comment does not remove the credential-handling problem, especially because the README presents the stack as independently deployable and the public post does not surface this limitation.

**Fix**

Do not put the JWT in `ClientMetadata`. Prefer a managed IdP with native RFC 8693/on-behalf-of support. If retaining the teaching exchange:

1. Validate the JWT at the exchange endpoint or verify-challenge trigger.
2. Store the verified claims in a short-lived encrypted record.
3. Put only a random, single-use handle in `ClientMetadata`.
4. Have the pre-token trigger atomically consume that handle.
5. Bind the record to the app client, service user, grant, and a short expiry.

At minimum, prominently document the credential-handling limitation in the README and post and state that this exchange must not be used with real customer tokens.

---

### 3. Major — Recreating a Cognito username gives the new identity access to the old customer’s orders

**Files and quotes**

- `agentcore/08-runtime-app/agent/main.py`:
  > “an administrator can delete a username and create it again for someone else”
- `agentcore/08-runtime-app/exchange/triggers.py`:
  > `"customer_id": claims["username"],`
- `agentcore/08-runtime-app/terraform/policy.tf`:
  > `principal.getTag("customer_id") == context.input.customer_id`
- `agentcore/08-runtime-app/tool/orders.py`:
  > `if r["customer_id"] == customer_id`

**Why it is wrong**

Memory correctly uses the immutable Cognito `sub`, but order authorization still uses the reusable `username`. If `c-1000` is deleted and later recreated, the new account has a different `sub` but receives `customer_id=c-1000` during token exchange. Cedar then permits calls for `c-1000`, and the tool returns the prior customer’s rows.

The code explicitly recognizes username reuse as an identity risk for memory but leaves the more sensitive order-data authorization path keyed by that same reusable value.

**Fix**

Authorize orders with a stable, non-reusable identifier:

- Map the verified Cognito `sub` to an internal Brightwell customer record, or
- Issue a controlled immutable customer identifier as a custom claim.

Put that identifier into the exchanged token, compare it in Cedar, and key/filter the order data by it. Do not derive the authorization subject directly from a reusable Cognito username.

---

### 4. Minor — Service-user creation can fail nondeterministically under Cognito’s password policy

**File and quote**

- `agentcore/08-runtime-app/terraform/exchange.tf`:
  > `resource "random_password" "service_user" { length = 32 special = true }`

**Why it is wrong**

The customer/exchange user pools use Cognito’s default password policy, which requires character classes including a digit, uppercase, lowercase, and symbol. Enabling those character sets in `random_password` does not guarantee that the generated value contains at least one character from each class. A generated password can therefore be rejected during `aws_cognito_user` creation.

**Fix**

Set explicit minima:

```hcl
resource "random_password" "service_user" {
  length      = 32
  special     = true
  min_lower   = 1
  min_upper   = 1
  min_numeric = 1
  min_special = 1
}
```

---

### 5. Minor — The image dependencies are not all pinned as claimed

**File and quote**

- `agentcore/08-runtime-app/agent/Dockerfile`:
  > “All pinned”
- `agentcore/08-runtime-app/README.md`:
  > “The pinned packages are demo 07's.”

**Why it is wrong**

Only the four direct requirements are version-pinned. Their transitive dependencies are resolved afresh by `pip`, and no hashes are enforced. A rebuild can therefore select different Starlette, Uvicorn, OpenTelemetry, MCP, or other transitive package versions even though the Dockerfile is unchanged. This is particularly relevant because the post relies on specific Starlette and ADOT instrumentation behavior.

The Dockerfile also says the README notes that packages are pinned by version rather than hash, but the supplied README does not make that qualification.

**Fix**

Build from a fully resolved lock file with exact transitive versions and hashes, for example via `pip-compile --generate-hashes`, then install with:

```dockerfile
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
```

Alternatively, change the claims to say only the direct dependencies are version-pinned and that transitive resolution is not reproducible.

not ready
