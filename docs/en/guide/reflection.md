---
title: Reflection
---

# Reflection

Server reflection is enabled by default. This makes your service discoverable by tooling and clients without distributing `.proto` files.

What you can do:

- Explore services and methods with `grpcurl` or Evans
- Generate clients dynamically
- Use FastGRPC’s Python client that leverages reflection

No extra setup is needed—reflection is registered when the server starts.

