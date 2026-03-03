# Quick Start: Push to GitHub & Deploy

## 1. Initialize Git (One Time)

```bash
cd /home/sizzyafro/Desktop/Website
git init
git add .
git commit -m "Initial commit: Dance with Sizzy Afro website"
```

## 2. Create GitHub Repository

1. Go to https://github.com/new
2. Name it: `sizzy-afro-website`
3. Click **Create repository**

## 3. Connect Local Repository to GitHub

Copy-paste these commands (use YOUR GitHub username):

```bash
git remote add origin https://github.com/YOUR_USERNAME/sizzy-afro-website.git
git branch -M main
git push -u origin main
```

That's it! Your code is now on GitHub.

## 4. Deploy to Render

1. Go to https://render.com and sign up with GitHub
2. Click **New Web Service**
3. Select your `sizzy-afro-website` repository
4. Render will auto-detect everything from `render.yaml`
5. Add environment variables (email, admin credentials)
6. Click **Deploy**

Your site will be live in 2-5 minutes!

## 5. Connect Your Domain

In Render settings → **Custom Domain** → Add `sizzyafro.me`

Then update DNS at your domain registrar with the CNAME Render gives you.

## 6. Future Updates

Every time you want to deploy new changes:

```bash
git add .
git commit -m "Your change description"
git push origin main
```

Render automatically re-deploys within 1-2 minutes!

---

**Full deployment instructions**: See [DEPLOYMENT.md](DEPLOYMENT.md)
