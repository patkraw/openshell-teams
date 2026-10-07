# Every agent, the lead included, runs in its own sandbox; OpenWorker's server stays on the host

Each OpenWorker agent (lead and every worker) runs in its own OpenShell sandbox, while OpenWorker's server, which holds the board, approvals and UI, runs on the host as a trusted service. We considered keeping the lead inside the server (less work) and running the whole server inside the lead's sandbox (reusing OpenWorker's in-sandbox work), but the first leaves the lead unconfined and the second lets a compromised lead rewrite the board and approval records.
