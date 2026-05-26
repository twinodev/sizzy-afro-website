<div align="center">

![Banner](https://capsule-render.vercel.app/api?type=waving&color=0:FF6B35,100:FF1493&height=200&section=header&text=Dance%20with%20Sizzy%20Afro&fontSize=40&fontColor=fff&animation=fadeIn&fontAlignY=38&desc=Afro%20Dance%20Classes%20%7C%20Events%20%7C%20Community&descAlignY=58&descSize=18)

[![Live Site](https://img.shields.io/badge/🌐%20Live%20Site-sizzyafro.me-FF6B35?style=for-the-badge)](https://www.sizzyafro.me)
[![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Deployed on Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com)

[![Instagram](https://img.shields.io/badge/Instagram-sizzyafro-E1306C?style=for-the-badge&logo=instagram&logoColor=white)](https://instagram.com/sizzyafro)
[![TikTok](https://img.shields.io/badge/TikTok-sizzyafro-000000?style=for-the-badge&logo=tiktok&logoColor=white)](https://tiktok.com/@sizzyafro)
[![YouTube](https://img.shields.io/badge/YouTube-sizzyafro-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://youtube.com/@sizzyafro)

</div>

---

## 📖 About The Project

**Dance with Sizzy Afro** is a full-stack web application for a community-first Afro dance brand based in Uganda. Built with **Flask** and powered by **Supabase (PostgreSQL)**, the platform helps dancers and creators grow their visibility, confidence, and community through vibrant classes, events, and performance culture.

> *"Rhythm. Culture. Community."*

---

## ✨ Key Features

- 🏠 **Dynamic Homepage** — Hero section, program highlights, and community stats
- 👤 **Artist Profile** — Showcase the dancer's identity, story, and style
- 📅 **Events Management** — Create, list, and manage upcoming dance events
- 📝 **Blog / Posts** — Dynamic news, camp recaps, and community stories
- 🛍️ **Merchandise Shop** — Brand merchandise for fans and dancers
- 🤝 **Sponsorships & Partnerships** — Dedicated pages for brand collaborations
- 🌍 **Community Hub** — Space for dancers to connect and grow
- 📬 **Newsletter Subscription** — Email capture and updates
- 💬 **WhatsApp Integration** — One-click session booking

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python, Flask |
| **Templating** | Jinja2 |
| **Database** | PostgreSQL via Supabase |
| **Frontend** | HTML5, CSS3, JavaScript |
| **Deployment** | Vercel |
| **Storage** | Supabase Storage |

### Badges

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=flat-square&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat-square&logo=postgresql&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-000000?style=flat-square&logo=vercel&logoColor=white)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat-square&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=flat-square&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black)

---

## 🌐 Live Demo

👉 **[www.sizzyafro.me](https://www.sizzyafro.me)**

| Page | URL |
|---|---|
| 🏠 Home | [sizzyafro.me](https://www.sizzyafro.me) |
| 👤 Profile | [sizzyafro.me/about](https://www.sizzyafro.me/about) |
| 📅 Events | [sizzyafro.me/events](https://www.sizzyafro.me/events) |
| 📝 Blog | [sizzyafro.me/posts](https://www.sizzyafro.me/posts) |
| 🛍️ Shop | [sizzyafro.me/merchandise](https://www.sizzyafro.me/merchandise) |
| 🌍 Community | [sizzyafro.me/community](https://www.sizzyafro.me/community) |
| 📬 Contact | [sizzyafro.me/contact](https://www.sizzyafro.me/contact) |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- pip
- A [Supabase](https://supabase.com) account with a PostgreSQL project
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/twinodev/sizzy-afro-website.git

# Navigate into the project folder
cd sizzy-afro-website

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the root directory:

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your_secret_key_here

# Supabase
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
DATABASE_URL=your_supabase_postgresql_connection_string
```

> ⚠️ Never commit your `.env` file. It is already in `.gitignore`.

### Running Locally

```bash
flask run
```

Visit `http://localhost:5000` in your browser.

---

## 📁 Project Structure

```
sizzy-afro-website/
│
├── app.py                  # Main Flask application & routes
├── requirements.txt        # Python dependencies
├── vercel.json             # Vercel deployment config
├── .env                    # Environment variables (not committed)
├── .gitignore
│
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Base layout
│   ├── index.html          # Homepage
│   ├── about.html          # Artist profile
│   ├── events.html         # Events page
│   ├── posts.html          # Blog listing
│   ├── post.html           # Single blog post
│   ├── merchandise.html    # Shop
│   ├── sponsors.html       # Sponsors
│   ├── partnerships.html   # Partnerships
│   ├── community.html      # Community hub
│   └── contact.html        # Contact page
│
└── static/
    ├── css/                # Stylesheets
    ├── js/                 # JavaScript files
    └── images/             # Static images & assets
```

---

## ☁️ Deployment

This app is deployed on **Vercel** with a **Supabase PostgreSQL** database.

### vercel.json config

```json
{
  "builds": [{ "src": "app.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "app.py" }]
}
```

### Deploy your own

1. Fork this repo
2. Create a Supabase project and copy your credentials
3. Import the repo into [Vercel](https://vercel.com)
4. Add environment variables in Vercel project settings
5. Deploy 🚀

---

## 📬 Contact & Booking

| Channel | Link |
|---|---|
| 🌐 Website | [sizzyafro.me/contact](https://www.sizzyafro.me/contact) |
| 💬 WhatsApp | [+256 758 359 591](https://wa.me/256758359591) |
| 📸 Instagram | [@sizzyafro](https://instagram.com/sizzyafro) |
| 🎵 TikTok | [@sizzyafro](https://tiktok.com/@sizzyafro) |

---

## 👨‍💻 Developer

Built and maintained with ❤️ by **Twinomujuni Emmanuel**

[![GitHub](https://img.shields.io/badge/GitHub-twinodev-181717?style=flat-square&logo=github)](https://github.com/twinodev)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Twinomujuni_Emmanuel-0A66C2?style=flat-square&logo=linkedin)](https://www.linkedin.com/in/twinomujuni-emmanuel-538783311)
[![Email](https://img.shields.io/badge/Email-tjuniemma@gmail.com-D14836?style=flat-square&logo=gmail)](mailto:tjuniemma@gmail.com)

---

## 📄 License

This project is proprietary and built for **Dance with Sizzy Afro**.
All rights reserved © 2026.

---

<div align="center">

![Footer](https://capsule-render.vercel.app/api?type=waving&color=0:FF1493,100:FF6B35&height=120&section=footer)

*Rhythm. Culture. Community.* 🕺🏾

</div>

3. Start the Flask server:
   ```bash
   python app.py
   ```

4. Open:
   - http://127.0.0.1:5000

## Admin Panel
- Login at `/admin/login`.
- Production deployments must set `ADMIN_PASSWORD`.
- Do not use shared or easy-to-guess admin credentials.

## Email Notifications
When configured, contact form submissions can send notifications to `ADMIN_EMAIL`.

For Brevo API:
- In the Brevo dashboard, create or copy your API key.
- Set `BREVO_API_KEY` to that key.
- Set `BREVO_SENDER_EMAIL` to a verified sender email in Brevo.
- Set `BREVO_SENDER_NAME` if you want a custom sender name.

## Tech
- Flask
- Tailwind CSS CDN
- Brevo API email delivery
- Flask-SQLAlchemy
- PostgreSQL/Supabase-ready storage configuration
