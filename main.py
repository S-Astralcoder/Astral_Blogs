import os

#gunicorn

import gunicorn

# Flask imports
from flask import Flask, render_template

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI")


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login")
def login():
    return render_template(
        "auth.html",
        page_title="Sign In",
        auth_title="Welcome Back",
        auth_subtitle="Sign in to continue reading, writing, and sharing with AstralBlogs.",
        submit_label="Sign In",
        switch_text="New here?",
        switch_label="Create an account",
        switch_href="/register",
    )


@app.route("/register")
def register():
    return render_template(
        "auth.html",
        page_title="Register",
        auth_title="Join AstralBlogs",
        auth_subtitle="Create your account and start building your place in the AstralBlogs community.",
        submit_label="Register",
        switch_text="Already have an account?",
        switch_label="Sign in here",
        switch_href="/login",
    )


if __name__ == "__main__":
    app.run(debug=True)
