from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import jwt, os, datetime
import logging

# Initialize logger
logger = logging.getLogger(__name__)

from models.user import UserCreate, UserInDB, UserOut
from main import db
from services.email_service import email_service

router = APIRouter()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET", "change_this_secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate, background_tasks: BackgroundTasks):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_pw = pwd_context.hash(user.password)
    user_in_db = UserInDB(**user.dict(exclude={"password"}), hashed_password=hashed_pw)
    doc = user_in_db.dict(by_alias=True)
    dob = doc.get('dob')
    if isinstance(dob, datetime.date):
        doc['dob'] = datetime.datetime(dob.year, dob.month, dob.day)
    result = await db.users.insert_one(doc)
    created = await db.users.find_one({"_id": result.inserted_id})
    
    # Send welcome email in the background
    try:
        background_tasks.add_task(
            email_service.send_welcome_email,
            user.email,
            user.first_name,
            user.last_name
        )
    except Exception as e:
        logger.error(f"Failed to queue welcome email task: {str(e)}")
        # Continue with user creation even if email fails
    
    return created

@router.post("/login", response_model=Token)
async def login(login_req: LoginRequest):
    user = await db.users.find_one({"email": login_req.email})
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    user_in_db = UserInDB(**user)
    if not pwd_context.verify(login_req.password, user_in_db.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_in_db.id), "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

    return user
