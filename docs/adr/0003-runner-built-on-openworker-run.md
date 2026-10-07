# The agent runner is built on `openworker run`, not on remote-machine mode

Each sandboxed agent runs an extended `openworker run`: its engine, OpenShell image and provider profiles, plus a long-lived loop, board tools over REST, wake-ups pulled from the server, and polled steer, chat and interrupt. Remote-machine mode (`openworker up`) looked closer because it is long-running and dials out, but each machine runs a whole OpenWorker server with its own sealed key store and a local board, so we reuse only its dial-out pattern.
