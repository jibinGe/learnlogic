from fastapi import FastAPI, Depends, HTTPException, status
from .routers import (users, testimonials, resources, themes, 
                      events, cart, purchases, billing, interest, 
                      email, stripe, password_reset, contact_form, admin, tutors)
from . import models, schemas, auth
from .database import engine, get_db
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from .config import settings
from sqlalchemy.orm import Session

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Records API",
    description="API for managing records with email notifications",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    # Case 1: Email not registered
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email address not found. Please try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Case 2: Tutor accounts must use the tutor login endpoint
    if user.user_type == models.UserType.TUTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tutor accounts must log in via the tutor login page.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Case 3: Wrong password
    if not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password. Please try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email, "user_type": user.user_type},
        expires_delta=access_token_expires
    )

    data = {
        "access_token": access_token,
        "user_id": user.id,
        "token_type": "bearer",
        "user_type": user.user_type
    }

    print(data)
    return data


@app.post("/tutor-token", response_model=schemas.Token)
async def tutor_login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    # Case 1: Email not registered
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email address not found. Please try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Case 2: Non-tutor accounts are not allowed here
    if user.user_type != models.UserType.TUTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This login is for tutor accounts only.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Case 3: Wrong password
    if not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password. Please try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email, "user_type": user.user_type},
        expires_delta=access_token_expires
    )

    data = {
        "access_token": access_token,
        "user_id": user.id,
        "token_type": "bearer",
        "user_type": user.user_type
    }

    print(data)
    return data


# Include routers
app.include_router(users.router)
app.include_router(testimonials.router)
app.include_router(resources.router)
app.include_router(themes.router)
app.include_router(events.router)
app.include_router(cart.router)
app.include_router(purchases.router)
app.include_router(billing.router)
app.include_router(interest.router)
app.include_router(email.router)
app.include_router(stripe.router)
app.include_router(password_reset.router)
app.include_router(contact_form.router)
app.include_router(admin.router)
app.include_router(tutors.router)
# Add a test root endpoint
@app.get("/")
def read_root():
    return {"updated at": "21-03-2025 Ver.1"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)