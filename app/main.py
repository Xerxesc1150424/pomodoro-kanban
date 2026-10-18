import os
import re
from typing import Optional
import uuid
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
import pdfplumber
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select

LA_TZ = ZoneInfo("America/Los_Angeles")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pomodoro.db")

if DATABASE_URL.startswith("postgres://"):
  DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
    ),
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(SQLModel, table=True):
  id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
  username: str = Field(unique=True, index=True)
  hashed_password: str


class Task(SQLModel, table=True):
  id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
  username: str = Field(index=True)
  title: str
  status: str = Field(default="todo")  # todo, pomodoro, in_progress, completed
  completed_pomodoros: int = Field(default=0)
  archived: bool = Field(default=False)


SQLModel.metadata.create_all(engine)

app = FastAPI(title="Pomodoro Kanban")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
  username: str
  password: str


class TaskCreate(BaseModel):
  username: str
  title: str


class TaskUpdate(BaseModel):
  status: Optional[str] = None
  completed_pomodoros: Optional[int] = None
  archived: Optional[bool] = None


@app.post("/api/register")
def register(auth: AuthRequest):
  username = auth.username.strip().lower()
  if not username or not auth.password:
    raise HTTPException(
        status_code=400, detail="Username and password required"
    )
  with Session(engine) as session:
    existing = session.exec(
        select(User).where(User.username == username)
    ).first()
    if existing:
      raise HTTPException(status_code=400, detail="Username already exists")
    hashed = pwd_context.hash(auth.password)
    user = User(username=username, hashed_password=hashed)
    session.add(user)
    session.commit()
    return {"message": "Registered successfully", "username": username}


@app.post("/api/login")
def login(auth: AuthRequest):
  username = auth.username.strip().lower()
  with Session(engine) as session:
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not pwd_context.verify(auth.password, user.hashed_password):
      raise HTTPException(
          status_code=401, detail="Invalid username or password"
      )
    return {"message": "Login successful", "username": username}


@app.get("/api/tasks")
def get_tasks(username: str):
  with Session(engine) as session:
    return session.exec(
        select(Task).where(
            Task.username == username.strip().lower(), Task.archived == False
        )
    ).all()


@app.get("/api/tasks/archived")
def get_archived_tasks(username: str):
  with Session(engine) as session:
    return session.exec(
        select(Task).where(
            Task.username == username.strip().lower(), Task.archived == True
        )
    ).all()


@app.post("/api/tasks")
def add_task(payload: TaskCreate):
  with Session(engine) as session:
    task = Task(username=payload.username.strip().lower(), title=payload.title)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate):
  with Session(engine) as session:
    task = session.get(Task, task_id)
    if not task:
      raise HTTPException(status_code=404, detail="Task not found")
    if payload.status is not None:
      task.status = payload.status
      if payload.status == "completed":
        task.archived = True
    if payload.completed_pomodoros is not None:
      task.completed_pomodoros = payload.completed_pomodoros
    if payload.archived is not None:
      task.archived = payload.archived
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
  with Session(engine) as session:
    task = session.get(Task, task_id)
    if not task:
      raise HTTPException(status_code=404, detail="Task not found")
    session.delete(task)
    session.commit()
    return {"deleted": True, "id": task_id}


def clean_pdf_task_line(line: str) -> Optional[str]:
  line = line.strip()
  if not line or len(line) < 4:
    return None

  # Discard calendar headers, dates, and upcoming section previews
  header_patterns = [
      r"^tasks?:",
      r"^(saturday|sunday|monday|tuesday|wednesday|thursday|friday)",
      r"^(morning|afternoon|evening|late afternoon):",
      r"^coming up",
      r"^•",
      r"^one 25-minute pomodoro",
      r"^tags?:",
      r"^albada \(skip",
      r"^boulder:",
  ]
  lower_line = line.lower()
  if any(re.search(pat, lower_line) for pat in header_patterns):
    return None

  # Strip leading checkmark symbols, pipes, or bullets
  text = re.sub(r"^[☐\s|•\-]+", "", line).strip()

  # Skip table header lines
  if re.match(r"^task\s*\|\s*\d*\s*\|\s*tag", text, re.IGNORECASE):
    return None
  if text.lower() in ["task", "tag", "reading", "boulder", "pm", "build"]:
    return None

  # If structured like "Task Title | 1 | Tag", extract the middle task segment
  if "|" in text:
    segments = [s.strip() for s in text.split("|") if s.strip()]
    if segments:
      if segments[0] in ["☐", "Π", ""] and len(segments) > 1:
        text = segments[1]
      else:
        text = segments[0]

  # Strip out trailing Pomodoro tally counts and tags at line ends
  text = re.sub(r"\s*\|\s*\d+(?:-\d+)?\s*\|\s*[A-Za-z]+.*$", "", text).strip()
  text = re.sub(
      r"\s*\|\s*(Reading|Boulder|PM|Build)$", "", text, re.IGNORECASE
  )
  text = re.sub(r"\s*\|\s*\d+(?:-\d+)?$", "", text).strip()

  # Remove inline due date prefixes
  text = re.sub(
      r"^optional,\s*due\s*[^:]+:\s*", "", text, re.IGNORECASE
  ).strip()

  # Exclude standalone numbers or single fragments
  if len(text) < 4 or text.isdigit():
    return None

  return text


@app.post("/api/upload-pdf")
async def upload_pdf(username: str, file: UploadFile = File(...)):
  contents = await file.read()
  temp_path = f"/tmp/{file.filename}"
  with open(temp_path, "wb") as f:
    f.write(contents)

  created_tasks = []
  seen_titles = set()

  with pdfplumber.open(temp_path) as pdf:
    for page in pdf.pages:
      text = page.extract_text() or ""
      for line in text.split("\n"):
        task_title = clean_pdf_task_line(line)
        if task_title and task_title not in seen_titles:
          seen_titles.add(task_title)
          created_tasks.append(
              Task(username=username.strip().lower(), title=task_title)
          )

  if os.path.exists(temp_path):
    os.remove(temp_path)

  with Session(engine) as session:
    for task in created_tasks:
      session.add(task)
    session.commit()

  return {"added_count": len(created_tasks)}


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
