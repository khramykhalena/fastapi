from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from redis import asyncio as aioredis
from datetime import timedelta
from typing import List, Optional

# Абсолютные импорты вместо относительных
from models import Base
from schemas import User, UserCreate, Token, Task, TaskCreate, TaskUpdate
from crud import (
    get_user_by_email,
    create_user,
    get_user_tasks,
    get_top_priority_tasks,
    create_user_task,
    get_task,
    update_task,
    delete_task
)
from auth import (
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_password_hash
)
from database import engine, get_db
from dependencies import get_current_user

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Task Manager API",
    description="API for managing tasks with authentication",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url("redis://localhost:6379")
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")

@app.post("/register/", response_model=User, tags=["Authentication"])
def register(user: UserCreate, db=Depends(get_db)):
    db_user = get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return create_user(db=db, user=user)

@app.post("/token", response_model=Token, tags=["Authentication"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db=Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/tasks/", response_model=Task, tags=["Tasks"])
def create_task(
    task: TaskCreate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if task.priority is None:
        task.priority = 1
    return create_user_task(db=db, task=task, user_id=current_user.id)

@app.get("/tasks/", response_model=List[Task], tags=["Tasks"])
@cache(expire=30)
def read_tasks(
    skip: int = 0,
    limit: int = 100,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
    search: Optional[str] = None,
    status: Optional[str] = None,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tasks = get_user_tasks(
        db, 
        user_id=current_user.id, 
        skip=skip, 
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        status=status
    )
    return tasks

@app.get("/tasks/top_priority/", response_model=List[Task], tags=["Tasks"])
@cache(expire=30)
def read_top_priority_tasks(
    n: int = 5,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tasks = get_top_priority_tasks(db, user_id=current_user.id, n=n)
    return tasks

@app.get("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
def read_task(
    task_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_task = get_task(db, task_id=task_id)
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if db_task.owner_id != current_user.id:
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return db_task

@app.put("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
def update_task(
    task_id: int,
    task: TaskUpdate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_task = get_task(db, task_id=task_id)
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if db_task.owner_id != current_user.id:
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return update_task(db=db, task_id=task_id, task=task)

@app.delete("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
def delete_task(
    task_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_task = get_task(db, task_id=task_id)
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if db_task.owner_id != current_user.id:
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return delete_task(db=db, task_id=task_id)

@app.get("/users/me/", response_model=User, tags=["Users"])
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
