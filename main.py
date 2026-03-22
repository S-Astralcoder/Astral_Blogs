import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_ckeditor import CKEditor
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length
from werkzeug.security import check_password_hash, generate_password_hash
from flask_ckeditor import CKEditorField


class Base(DeclarativeBase):
    pass


app = Flask(__name__, instance_relative_config=True)
app.config["SECRET_KEY"] = os.environ.get("FLASK_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DB_URI")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

ADMIN_NAME = os.environ.get("ADMIN_NAME")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

db = SQLAlchemy(model_class=Base)
db.init_app(app)
ckeditor = CKEditor(app)


class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=180)])
    subtitle = StringField("Subtitle", validators=[DataRequired(), Length(max=240)])
    content = CKEditorField("Post Content", validators=[DataRequired()])
    submit = SubmitField("Publish Post")


class CommentForm(FlaskForm):
    comment = TextAreaField("Comment", validators=[DataRequired(), Length(max=2000)])
    submit = SubmitField("Post Comment")


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    email: Mapped[str] = mapped_column(db.String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    posts: Mapped[list["Post"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship(back_populates="author", cascade="all, delete-orphan")


class Post(db.Model):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(db.String(180), nullable=False)
    subtitle: Mapped[str] = mapped_column(db.String(240), nullable=False)
    content: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    author_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False)

    author: Mapped[User] = relationship(back_populates="posts")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="Comment.created_at.desc()",
    )


class Comment(db.Model):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    author_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False)
    post_id: Mapped[int] = mapped_column(db.ForeignKey("posts.id"), nullable=False)

    author: Mapped[User] = relationship(back_populates="comments")
    post: Mapped[Post] = relationship(back_populates="comments")


def is_admin(user):
    return bool(user and user.email == ADMIN_EMAIL and user.name.strip().lower() == ADMIN_NAME)


def can_manage_post(user, post):
    return bool(user and (is_admin(user) or post.author_id == user.id))



def ensure_admin_user():
    admin_user = db.session.execute(
        db.select(User).where(User.email == ADMIN_EMAIL)
    ).scalar_one_or_none()

    if admin_user is None:
        admin_user = User(
            name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            password_hash=generate_password_hash(DEFAULT_ADMIN_PASSWORD),
        )
        db.session.add(admin_user)
        db.session.commit()
        return

    updated = False
    if admin_user.name != ADMIN_NAME:
        admin_user.name = ADMIN_NAME
        updated = True

    if not admin_user.password_hash:
        admin_user.password_hash = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
        updated = True

    if updated:
        db.session.commit()


with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()
    ensure_admin_user()


@app.before_request
def load_current_user():
    user_id = session.get("user_id")
    g.current_user = db.session.get(User, user_id) if user_id else None


@app.context_processor
def inject_current_user():
    current_user = g.get("current_user")
    return {
        "current_user": current_user,
        "is_admin_user": is_admin(current_user),
        "can_manage_post": can_manage_post,
    }


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.current_user is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def home():
    latest_posts = (
        db.session.execute(db.select(Post).order_by(Post.created_at.desc()).limit(3)).scalars().all()
    )
    return render_template("home.html", latest_posts=latest_posts, page_title="Astral Blogs")


@app.route("/posts")
def posts():
    all_posts = db.session.execute(db.select(Post).order_by(Post.created_at.desc())).scalars().all()
    return render_template("blogs_page.html", page_title="All Posts", posts=all_posts)


@app.route("/posts/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    post = db.get_or_404(Post, post_id)
    comment_form = CommentForm()

    if request.method == "POST":
        if g.current_user is None:
            flash("Please sign in to comment on this post.", "warning")
            return redirect(url_for("login"))

        if not comment_form.validate_on_submit():
            flash("Comment cannot be empty.", "error")
            return render_template("blog.html", page_title=post.title, post=post, comment_form=comment_form)

        db.session.add(
            Comment(
                content=comment_form.comment.data.strip(),
                author=g.current_user,
                post=post,
            )
        )
        db.session.commit()
        flash("Comment posted.", "success")
        return redirect(url_for("show_post", post_id=post.id))

    return render_template("blog.html", page_title=post.title, post=post, comment_form=comment_form)


@app.route("/posts/new", methods=["GET", "POST"])
@login_required
def create_post():
    form = PostForm()
    if request.method == "POST":
        if not form.validate_on_submit():
            flash("Title, subtitle, and content are required.", "error")
            return render_template("post_form.html", page_title="Write a Post", form=form, form_mode="create")

        new_post = Post(
            title=form.title.data.strip(),
            subtitle=form.subtitle.data.strip(),
            content=form.content.data.strip(),
            author=g.current_user,
        )
        db.session.add(new_post)
        db.session.commit()
        flash("Your post is now live.", "success")
        return redirect(url_for("show_post", post_id=new_post.id))

    return render_template("post_form.html", page_title="Write a Post", form=form, form_mode="create")


@app.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)
    if not can_manage_post(g.current_user, post):
        flash("You can only edit your own posts.", "error")
        return redirect(url_for("show_post", post_id=post.id))

    form = PostForm(obj=post)
    if request.method == "POST":
        if not form.validate_on_submit():
            flash("Title, subtitle, and content are required.", "error")
            return render_template(
                "post_form.html",
                page_title="Edit Post",
                form=form,
                form_mode="edit",
                post=post,
            )

        post.title = form.title.data.strip()
        post.subtitle = form.subtitle.data.strip()
        post.content = form.content.data.strip()
        db.session.commit()
        flash("Post updated.", "success")
        return redirect(url_for("show_post", post_id=post.id))

    return render_template(
        "post_form.html",
        page_title="Edit Post",
        form=form,
        form_mode="edit",
        post=post,
    )


@app.route("/posts/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    if not can_manage_post(g.current_user, post):
        flash("You can only delete your own posts.", "error")
        return redirect(url_for("show_post", post_id=post.id))

    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("posts"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm-password", "")

        if not name or not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template(
                "auth.html",
                page_title="Register",
                auth_title="Join AstralBlogs",
                auth_subtitle="Create your account and start building your place in the AstralBlogs community.",
                submit_label="Register",
                switch_text="Already have an account?",
                switch_label="Sign in here",
                switch_href=url_for("login"),
            )

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        if email == ADMIN_EMAIL:
            name = ADMIN_NAME

        existing_user = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
        if existing_user:
            flash("That email is already registered. Please sign in instead.", "warning")
            return redirect(url_for("login"))

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        flash("Your account has been created.", "success")
        return redirect(url_for("posts"))

    return render_template(
        "auth.html",
        page_title="Register",
        auth_title="Join AstralBlogs",
        auth_subtitle="Create your account and start building your place in the AstralBlogs community.",
        submit_label="Register",
        switch_text="Already have an account?",
        switch_label="Sign in here",
        switch_href=url_for("login"),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect(url_for("login"))

        user = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
        if user is None or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        flash("Welcome back.", "success")
        return redirect(url_for("posts"))

    return render_template(
        "auth.html",
        page_title="Sign In",
        auth_title="Welcome Back",
        auth_subtitle="Sign in to continue reading, writing, and sharing with AstralBlogs.",
        submit_label="Sign In",
        switch_text="New here?",
        switch_label="Create an account",
        switch_href=url_for("register"),
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
