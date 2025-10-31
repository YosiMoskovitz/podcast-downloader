# Google OAuth setup for this project

This document explains how to create the Google Cloud project and OAuth credentials required by this application, how to obtain the client ID / client secret / project ID, and how to add test users so the app is allowed to access Google APIs while in testing.

It also explains options for publishing the app (verifying) so non-test users can use it.

## Quick summary (what this repo expects)

- The repository expects OAuth client credentials to be available in `config/credentials.json` (the same shape produced by Google's "OAuth Client ID" download). A sample file already exists at `config/credentials.json`.
- At runtime the app will store user tokens in `token.json`. Do NOT commit `token.json` or your client secret to source control.

## Prerequisites

- A Google account with permission to create projects in Google Cloud Console.
- The app needs one or more APIs enabled (for example: Google Drive API) depending on which features you use.

## Step-by-step: create project and OAuth credentials

1. Open Google Cloud Console: https://console.cloud.google.com/

2. Create or select a Project
   - Click the project dropdown (top bar) -> New Project.
   - Enter a Project name and click Create.
   - After creation, note the Project ID (you'll need it). The Project ID appears on the project dashboard and is also included in downloaded credentials JSON.

3. Enable required APIs
   - In the left menu, choose "APIs & Services" → "Library".
   - Search for the APIs your app needs (for example: "Google Drive API") and click Enable.

4. Configure the OAuth consent screen
   - In "APIs & Services" → "OAuth consent screen".
   - Choose User Type:
     - Internal — only available to accounts in your Google Workspace organization.
     - External — recommended for public apps or testing with external Gmail accounts.
   - Fill in the required fields:
     - App name
     - User support email
     - Developer contact email(s)
   - Under Scopes, add the scopes your app will request (for Drive access, add the appropriate Drive scopes such as `../auth/drive.file`).
   - Save and continue.

5. Add Test Users (important for External apps in testing)
   - If you selected External and haven't published the app, the app will be in "Testing" mode. Only users explicitly added as Test users can complete the OAuth flow without verification.
   - In the OAuth consent screen page, find the "Test users" section and add the email addresses (Google accounts) that will sign in during development/testing.
   - Save the changes. Test users will now be able to authorize the app.

6. Create OAuth 2.0 Client ID (credentials)
   - Go to "APIs & Services" → "Credentials" → "Create credentials" → "OAuth client ID".
   - Select an Application type:
     - Desktop app — simple local flows, will produce a JSON with an `installed` key (works well for local scripts).
     - Web application — for apps running on a web server. You'll need to set Authorized redirect URIs.
   - Give it a name (e.g., "Podcast Downloader - Local").
   - If you chose Web application, set Authorized redirect URIs. Example common values for local testing:
     - http://localhost
     - http://localhost:5000/oauth2callback
     Use the redirect URI that matches how the app performs the OAuth callback. If you are not sure, check the code that initiates the OAuth flow and note the redirect URI it expects.
   - Click Create.
   - Download the JSON file that is offered (Click the download icon). This file contains `client_id`, `client_secret`, and `project_id`.

7. Place credentials in this repository
   - The easiest approach for this repo is to copy the downloaded JSON into `config/credentials.json` (overwrite or edit as needed). The repository already contains a sample `config/credentials.json`.
   - If the downloaded JSON is of type `web` (has a top-level `web` block) and the repo expects an `installed` block, you can either:
     - Keep the downloaded structure and update the code that loads credentials (advanced), or
     - Copy the important fields into `config/credentials.json` using the same structure the app expects (client_id, client_secret, project_id, redirect_uris).

   Example minimal structure the app recognizes (from `config/credentials.json` already in repo):

   {
     "installed": {
       "client_id": "<YOUR_CLIENT_ID>",
       "project_id": "<YOUR_PROJECT_ID>",
       "client_secret": "<YOUR_CLIENT_SECRET>",
       "redirect_uris": ["http://localhost"]
     }
   }

   - After placing the credentials, keep the file locally and secure. Do not push these secrets to public repositories.

8. Run the app and complete the OAuth flow as a Test User
   - Start the application (for local runs, your app will typically open a browser for the OAuth consent screen or print a URL to visit).
   - Sign in with an account that you added as a Test user in step 5.
   - After granting consent, the app will receive tokens and write them to `token.json` (or an equivalent path). Again, do not commit `token.json`.

## Publishing and verification (so non-test users can use the app)

- If you want any Google user to be able to sign in (not only Test users), you must publish the OAuth consent screen. For some scopes (sensitive or restricted scopes such as full Drive access) Google requires verification which may involve:
  - Adding a privacy policy URL and homepage on a verified domain
  - Domain verification in Google Search Console
  - A verification review by Google (can take days and require screencasts, restricted scope justification, and more)
- To publish: OAuth consent screen → click "Publish App" (or follow prompts to submit for verification if requested). Follow Google's instructions for verification.
- If the app requests only non-sensitive scopes and is for limited internal use, you might never need verification; but sensitive scopes used with an external app usually require review.

## Common issues and troubleshooting

- "This app isn't verified":
  - If you are a Test user, this warning is expected while the app is in testing; you can proceed by choosing "Advanced" → "Go to <app name> (unsafe)". To remove the warning for all users, submit the app for verification and publish.
  - Alternatively, add the user as a Test user (OAuth consent screen → Test users).

- "Redirect URI mismatch" errors:
  - Add the exact redirect URI printed in the error message to the OAuth Client's Authorized Redirect URIs in the Credentials page.

- "insufficient permission" or scope errors:
  - Ensure the scope your app requests is enabled in the API Library and that the scope is listed in the OAuth consent screen configuration.

## Security notes

- Never commit `config/credentials.json` with the client secret to a public repository.
- Add `token.json` and any runtime secrets to `.gitignore` (if not already ignored).
- For production deployments, store client secrets in environment variables or your CI secret store rather than in repository files.

## Useful links

- Google Cloud Console: https://console.cloud.google.com/
- Create OAuth client ID (Docs): https://developers.google.com/identity/protocols/oauth2
- OAuth consent screen documentation: https://support.google.com/cloud/answer/6158849
- OAuth verification: https://support.google.com/cloud/answer/9110914

## Where to get help

If you run into errors, collect the full error message and search Google's documentation first. If you still need help, open an issue in this repository with the error text and a short description of what you tried.

---

If you'd like, I can also:

- Add a short script to automatically place the downloaded credentials JSON into `config/credentials.json`.
- Add `.gitignore` entries for `token.json` and `config/credentials.json` (if you want them ignored by default).

Let me know if you want me to add either of those changes.
