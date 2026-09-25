"""Main FastAPI application module for the blog application.

Provides HTML template routes for the frontend, RESTful API endpoints for
managing users and posts, and custom exception handlers.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
from database import Base, engine, get_db
from schemas import (
    PostCreate,
    PostResponse,
    PostUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Blog Application API",
    description="A blogging platform providing web views and RESTful API endpoints.",
    version="0.1.0",
)

# Static and media files mounting
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

# Templates configuration
templates = Jinja2Templates(directory="templates")

# Dependency type alias for database session
DbSession = Annotated[Session, Depends(get_db)]


# ==============================================================================
# HTML Template Routes
# ==============================================================================


@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
def home(request: Request, db: DbSession) -> Response:
    """Render the home page displaying all blog posts."""
    result = db.execute(select(models.Post))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "home.html",
        {"posts": posts, "title": "Home"},
    )


@app.get("/posts/{post_id}", include_in_schema=False, name="post_page")
def post_page(request: Request, post_id: int, db: DbSession) -> Response:
    """Render the detailed view page for a specific post."""
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    title = post.title[:50]
    return templates.TemplateResponse(
        request,
        "post.html",
        {"post": post, "title": title},
    )


@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
def user_posts_page(request: Request, user_id: int, db: DbSession) -> Response:
    """Render the page displaying all posts authored by a specific user."""
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    result = db.execute(select(models.Post).where(models.Post.user_id == user_id))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"posts": posts, "user": user, "title": f"{user.username}'s Posts"},
    )


# ==============================================================================
# User API Endpoints
# ==============================================================================


@app.post(
    "/api/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Users"],
)
def create_user(user: UserCreate, db: DbSession) -> models.User:
    """Create a new user.

    Validates that both the username and email are unique before creating
    the user record in the database.
    """
    result = db.execute(
        select(models.User).where(models.User.username == user.username)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    result = db.execute(select(models.User).where(models.User.email == user.email))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.get(
    "/api/users/{user_id}",
    response_model=UserResponse,
    tags=["Users"],
)
def get_user(user_id: int, db: DbSession) -> models.User:
    """Retrieve a single user by ID."""
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@app.get(
    "/api/users/{user_id}/posts",
    response_model=list[PostResponse],
    tags=["Users"],
)
def get_user_posts(user_id: int, db: DbSession) -> list[models.Post]:
    """Retrieve all posts authored by a specific user."""
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    result = db.execute(select(models.Post).where(models.Post.user_id == user_id))
    return list(result.scalars().all())


@app.patch(
    "/api/users/{user_id}",
    response_model=UserResponse,
    tags=["Users"],
)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: DbSession,
) -> models.User:
    """Update profile information for an existing user."""
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user_update.username is not None and user_update.username != user.username:
        result = db.execute(
            select(models.User).where(models.User.username == user_update.username)
        )
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

    if user_update.email is not None and user_update.email != user.email:
        result = db.execute(
            select(models.User).where(models.User.email == user_update.email)
        )
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    if user_update.username is not None:
        user.username = user_update.username
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.image_file is not None:
        user.image_file = user_update.image_file

    db.commit()
    db.refresh(user)
    return user


@app.delete(
    "/api/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Users"],
)
def delete_user(user_id: int, db: DbSession) -> None:
    """Delete a user by ID."""
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    db.delete(user)
    db.commit()


# ==============================================================================
# Post API Endpoints
# ==============================================================================


@app.post(
    "/api/posts",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Posts"],
)
def create_post(post: PostCreate, db: DbSession) -> models.Post:
    """Create a new blog post."""
    result = db.execute(select(models.User).where(models.User.id == post.user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    new_post = models.Post(
        title=post.title,
        content=post.content,
        user_id=post.user_id,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post


@app.get(
    "/api/posts",
    response_model=list[PostResponse],
    tags=["Posts"],
)
def get_posts(db: DbSession) -> list[models.Post]:
    """Retrieve all blog posts."""
    result = db.execute(select(models.Post))
    return list(result.scalars().all())


@app.get(
    "/api/posts/{post_id}",
    response_model=PostResponse,
    tags=["Posts"],
)
def get_post(post_id: int, db: DbSession) -> models.Post:
    """Retrieve a single blog post by ID."""
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    return post


@app.put(
    "/api/posts/{post_id}",
    response_model=PostResponse,
    tags=["Posts"],
)
def update_post_full(
    post_id: int,
    post_data: PostCreate,
    db: DbSession,
) -> models.Post:
    """Fully replace/update an existing blog post."""
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post_data.user_id != post.user_id:
        result = db.execute(
            select(models.User).where(models.User.id == post_data.user_id)
        )
        user = result.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    db.commit()
    db.refresh(post)
    return post


@app.patch(
    "/api/posts/{post_id}",
    response_model=PostResponse,
    tags=["Posts"],
)
def update_post_partial(
    post_id: int,
    post_data: PostUpdate,
    db: DbSession,
) -> models.Post:
    """Partially update an existing blog post."""
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    update_data = post_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)
    return post


@app.delete(
    "/api/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Posts"],
)
def delete_post(post_id: int, db: DbSession) -> None:
    """Delete a blog post by ID."""
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    db.delete(post)
    db.commit()


# ==============================================================================
# Custom Exception Handlers
# ==============================================================================


@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(
    request: Request,
    exception: StarletteHTTPException,
) -> Response:
    """Handle Starlette and FastAPI HTTP exceptions for both API and HTML routes."""
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={"detail": message},
        )
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": str(exception.status_code),
            "message": message,
        },
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
def validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
) -> Response:
    """Handle request validation errors for both API and HTML routes."""
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exception.errors()},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "title": str(status.HTTP_422_UNPROCESSABLE_ENTITY),
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
