import os
import re
from typing import Optional
import uuid
from zoneinfo import ZoneInfo
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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


class TaskCreate(BaseModel):
  username: str
  title: str


class TaskUpdate(BaseModel):
  status: Optional[str] = None
  completed_pomodoros: Optional[int] = None
  archived: Optional[bool] = None


@app.get("/api/tasks")
def get_tasks(username: str):
  with Session(engine) as session:
    # Only return active, unarchived board tasks
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
      # When marked completed, immediately archive
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


@app.post("/api/upload-pdf")
async def upload_pdf(username: str, file: UploadFile = File(...)):
  contents = await file.read()
  temp_path = f"/tmp/{file.filename}"
  with open(temp_path, "wb") as f:
    f.write(contents)

  created_tasks = []
  with pdfplumber.open(temp_path) as pdf:
    for page in pdf.pages:
      text = page.extract_text() or ""
      for line in text.split("\n"):
        clean_line = line.strip()
        if clean_line and len(clean_line) > 3:
          task = Task(username=username.strip().lower(), title=clean_line)
          created_tasks.append(task)

  if os.path.exists(temp_path):
    os.remove(temp_path)

  with Session(engine) as session:
    for task in created_tasks:
      session.add(task)
    session.commit()

  return {"added_count": len(created_tasks)}


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
