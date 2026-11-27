# Free private online test (GitHub Codespaces)

This is a development preview, not a public production deployment. Use a personal GitHub account with remaining included Codespaces compute/storage, choose the smallest 2-core machine, and keep port 8000 private. Check the account's usage and spending limits before creating the codespace; stop it after testing. Do not upload real student records.

1. In GitHub Settings → Codespaces → Secrets, create personal development secrets for this repository: GEMINI_API_KEY, OPENROUTER_API_KEY, BAZAARLINK_API_KEY. These are the same key values you used in Actions under GEMEINI, OPENROUTER and SOME. Actions secrets are separate and cannot be read or transferred. Never enter keys in chat, commit them or expose them in a browser.
2. Open https://github.com/codespaces/new?repo=7clan/projectpro and create a codespace for main using the DÉCLIC configuration. The setup installs the same Python backend, OCR, Piper and both Vosk models. The server starts automatically.
3. In Ports, open DÉCLIC on port 8000 in Browser. Keep visibility Private; GitHub authentication protects the forwarded URL. The actual URL is created by GitHub and is not known before launch.
4. For Ollama, run `bash .devcontainer/enable-ollama.sh` in the terminal. This downloads the small Qwen model and restarts the server with the fourth provider enabled. All cloud credentials are preserved. Ollama runs on the remote Codespace CPU, not your laptop. Use the app's AI mode selector. Port 11434 must not be forwarded.
5. Test with synthetic documents and dummy accounts. If microphone fails, open the application in a top-level browser tab and check site permissions. WebSocket behavior through the Codespaces proxy still requires actual acceptance testing.
6. Stop the codespace from https://github.com/codespaces after testing. Files in the retained workspace persist but deleting it deletes the database; export or back up anything important first. Codespace storage consumes the included allowance even when stopped.

This setup has not been deployed into your account. The app's actual performance, quotas, forwarded microphone connection and persistence must be tested there. Do not make the port public: the current pilot lacks production-grade authentication, abuse protection and operational controls. For an independent permanent public host, provision and review a separate VM and deployment.

Official docs: https://docs.github.com/en/billing/concepts/product-billing/github-codespaces ; https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace ; https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces
