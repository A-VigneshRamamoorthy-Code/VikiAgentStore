---
name: vercel-deploy
description: >
  Deploys a web application to Vercel and configures custom DNS records.
  Handles initializing vercel.json, asking the user for a token if needed, deploying to production,
  linking custom domains, and providing DNS instructions for the registrar.
license: MIT
metadata:
  author: Copilot Research
  version: "1.0.0"
---

# Vercel Deployment & DNS Configuration Skill

Use this skill when the user asks to deploy their web application to Vercel and/or link it to a custom domain (e.g., Squarespace, GoDaddy, etc.).

## Steps to Execute:

### 1. Preparation
- Create or verify a `vercel.json` file in the project root with the correct `buildCommand`, `outputDirectory`, and `framework` (e.g. `vite`, `nextjs`, etc.).

### 2. Authentication & Deployment
- Instruct the user to log in if they aren't already authenticated, or use `npx vercel login`.
- Run `npx vercel --prod --yes` to deploy the application to Vercel.

### 3. Domain Configuration
- If the user provides a custom domain (e.g., `example.com`), run `npx vercel domains add example.com`.
- Run `npx vercel domains inspect example.com` to fetch the required DNS records (A and CNAME).

### 4. Provide DNS Instructions
- If the registrar doesn't have an automated integration (like Squarespace), provide the user with clear instructions to update their DNS records:
  - Add an **A record** for `@` pointing to `76.76.21.21` (or the IP Vercel provides).
  - Add a **CNAME record** for `www` pointing to `cname.vercel-dns.com`.
- Explain that DNS propagation can take 15-30 minutes and the SSL certificate will be issued automatically once propagation completes.
