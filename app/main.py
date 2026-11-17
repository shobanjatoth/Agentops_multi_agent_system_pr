# """
# FastAPI entrypoint.

# POST /tasks              -> kicks off ONE task, streams each node's result via SSE
# POST /tasks/batch        -> processes MULTIPLE tasks concurrently (semaphore-bounded)
# POST /tasks/{id}/approve -> human resolves a pending approval-gate task
# GET  /tasks/{id}          -> poll current status/trace for a task
# GET  /metrics             -> system-wide aggregate observability metrics
# GET  /health               -> liveness probe
# """
# from __future__ import annotations

# import asyncio
# import json
# import os
# import time
# import uuid
# from contextlib import asynccontextmanager

# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel, Field, field_validator
# from sse_starlette.sse import EventSourceResponse

# from app.approval import approval_store
# from app.eval_tracker import EvalTracker, aggregate_metrics, init_db
# from app.graph import build_graph, build_tool_registry
# from app.llm import LLMClient

# load_dotenv()

# # Bounds how many tasks run through the graph at once — protects the LLM
# # provider's rate limit while still processing a batch concurrently
# # instead of one-at-a-time. Same pattern as RepoMind AI's Semaphore-bounded
# # multi-issue processing.
# MAX_CONCURRENT_TASKS = max(1, min(int(os.getenv("MAX_CONCURRENT_TASKS", "3")), 10))
# MAX_BATCH_SIZE = max(1, min(int(os.getenv("MAX_BATCH_SIZE", "20")), 100))
# _task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


# @asynccontextmanager
# async def lifespan(_app: FastAPI):
#     init_db()
#     yield


# app = FastAPI(title="AgentOps", version="1.1.0", lifespan=lifespan)

# tool_registry = build_tool_registry()


# class TaskRequest(BaseModel):
#     description: str = Field(min_length=1, max_length=8_000)
#     repo: str | None = None

#     @field_validator("description")
#     @classmethod
#     def strip_description(cls, value: str) -> str:
#         value = value.strip()
#         if not value:
#             raise ValueError("description cannot be blank")
#         return value

#     @field_validator("repo")
#     @classmethod
#     def validate_repo(cls, value: str | None) -> str | None:
#         if value is None:
#             return None
#         value = value.strip()
#         import re
#         parts = value.split("/")
#         if (
#             not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)
#             or any(part in {".", ".."} or part.startswith(".") for part in parts)
#         ):
#             raise ValueError("repo must be a GitHub owner/repository slug")
#         return value


# class BatchTaskRequest(BaseModel):
#     tasks: list[TaskRequest]


# class ApprovalRequest(BaseModel):
#     approved: bool


# async def _run_single_task(description: str, repo: str | None, llm: LLMClient | None = None) -> dict:
#     """
#     Shared execution path used by both /tasks/batch and (conceptually)
#     /tasks: builds a fresh tracker + graph, runs it to completion, and
#     normalizes the result into one dict. Bounded by `_task_semaphore` so
#     a batch of N tasks never fires more than MAX_CONCURRENT_TASKS LLM
#     calls at once.
#     """
#     task_id = str(uuid.uuid4())
#     tracker = EvalTracker(task_id=task_id)
#     tracker.start_task(description)

#     async with _task_semaphore:
#         start = time.perf_counter()
#         graph = build_graph(tracker=tracker, llm=llm or LLMClient(), tools=tool_registry)
#         initial_state = {
#             "task_id": task_id,
#             "description": description,
#             "repo": repo,
#             "status": "pending",
#             "trace": [],
#             "tool_calls": [],
#             "context_snippets": [],
#             "revision_count": 0,
#         }
#         try:
#             final_state = await graph.ainvoke(initial_state)
#         except Exception as exc:  # noqa: BLE001 — surfaced per-task, not raised to the batch
#             tracker.update_task_status("failed")
#             return {
#                 "task_id": task_id,
#                 "description": description,
#                 "status": "failed",
#                 "error": str(exc),
#                 "wall_clock_ms": round((time.perf_counter() - start) * 1000, 1),
#             }

#         wall_clock_ms = round((time.perf_counter() - start) * 1000, 1)

#         if final_state.get("requires_human_approval"):
#             approval_store.add(task_id, final_state["proposed_action"], final_state["risk_score"])
#             tracker.update_task_status("awaiting_approval", requires_human_approval=True)
#         else:
#             tracker.update_task_status("done")

#         return {
#             "task_id": task_id,
#             "description": description,
#             "status": final_state.get("status"),
#             "category": final_state.get("category"),
#             "priority": final_state.get("priority"),
#             "proposed_action": final_state.get("proposed_action"),
#             "risk_score": final_state.get("risk_score"),
#             "requires_human_approval": final_state.get("requires_human_approval", False),
#             "wall_clock_ms": wall_clock_ms,
#             "summary": tracker.task_summary(),
#         }


# @app.get("/health")
# def health():
#     return {"status": "ok", "approval_store_backend": approval_store.backend}


# @app.get("/metrics")
# def metrics():
#     return aggregate_metrics()


# @app.post("/tasks")
# async def create_task(req: TaskRequest):
#     task_id = str(uuid.uuid4())
#     tracker = EvalTracker(task_id=task_id)
#     tracker.start_task(req.description)

#     async def event_stream():
#         graph = build_graph(tracker=tracker, llm=LLMClient(), tools=tool_registry)
#         initial_state = {
#             "task_id": task_id,
#             "description": req.description,
#             "repo": req.repo,
#             "status": "pending",
#             "trace": [],
#             "tool_calls": [],
#             "context_snippets": [],
#             "revision_count": 0,
#         }

#         final_state = None
#         async for event in graph.astream(initial_state):
#             for node_name, node_output in event.items():
#                 final_state = node_output
#                 yield {
#                     "event": "node_complete",
#                     "data": json.dumps(
#                         {
#                             "node": node_name,
#                             "status": node_output.get("status"),
#                             "trace_tail": node_output.get("trace", [])[-1]
#                             if node_output.get("trace")
#                             else None,
#                         }
#                     ),
#                 }

#         if final_state and final_state.get("requires_human_approval"):
#             approval_store.add(
#                 task_id, final_state["proposed_action"], final_state["risk_score"]
#             )
#             tracker.update_task_status("awaiting_approval", requires_human_approval=True)
#             yield {
#                 "event": "awaiting_approval",
#                 "data": json.dumps(
#                     {
#                         "task_id": task_id,
#                         "action": final_state["proposed_action"],
#                         "risk_score": final_state["risk_score"],
#                     }
#                 ),
#             }
#         else:
#             tracker.update_task_status("done")
#             yield {"event": "done", "data": json.dumps(tracker.task_summary())}

#     return EventSourceResponse(event_stream())


# @app.post("/tasks/batch")
# async def create_tasks_batch(req: BatchTaskRequest):
#     """
#     Processes multiple tasks concurrently, bounded by MAX_CONCURRENT_TASKS
#     (default 3). Unlike POST /tasks, this is not streamed — it returns
#     once every task in the batch has either completed or hit the
#     approval gate. Useful for triaging a backlog of tickets in one call
#     instead of N sequential requests.
#     """
#     if not req.tasks:
#         raise HTTPException(status_code=400, detail="tasks list cannot be empty")
#     if len(req.tasks) > MAX_BATCH_SIZE:
#         raise HTTPException(status_code=422, detail=f"tasks list cannot exceed {MAX_BATCH_SIZE} items")

#     start = time.perf_counter()
#     results = await asyncio.gather(
#         *[_run_single_task(t.description, t.repo) for t in req.tasks]
#     )
#     total_wall_clock_ms = round((time.perf_counter() - start) * 1000, 1)

#     return {
#         "batch_size": len(req.tasks),
#         "max_concurrent": MAX_CONCURRENT_TASKS,
#         "max_batch_size": MAX_BATCH_SIZE,
#         "total_wall_clock_ms": total_wall_clock_ms,
#         "results": results,
#     }


# @app.post("/tasks/{task_id}/approve")
# def approve_task(task_id: str, req: ApprovalRequest):
#     resolved = approval_store.resolve(task_id, req.approved)
#     if resolved is None:
#         raise HTTPException(status_code=404, detail="No pending approval for this task_id")

#     tracker = EvalTracker(task_id=task_id)
#     tracker.update_task_status(
#         "done" if req.approved else "failed",
#         requires_human_approval=True,
#         approved=req.approved,
#     )
#     return {
#         "task_id": task_id,
#         "approved": req.approved,
#         "action": resolved["action"],
#         # Approval authorizes a proposed action. Execution is intentionally
#         # separate so a request cannot claim that an external side effect ran
#         # when no tool invocation occurred.
#         "executed": False,
#         "authorization_status": "approved" if req.approved else "rejected",
#     }


# @app.get("/tasks/{task_id}")
# def get_task(task_id: str):
#     tracker = EvalTracker(task_id=task_id)
#     return tracker.task_summary()


# @app.get("/tasks/pending/approvals")
# def list_pending_approvals():
#     return approval_store.pending()














# from __future__ import annotations

# import asyncio
# import json
# import os
# import re
# import time
# import uuid
# from contextlib import asynccontextmanager
# from app.executor import execute_action
# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel, Field, field_validator
# from sse_starlette.sse import EventSourceResponse

# from app.approval import approval_store
# from app.eval_tracker import (
#     EvalTracker,
#     aggregate_metrics,
#     dashboard_query,
#     dashboard_tasks,
#     init_db,
# )
# from app.graph import build_graph, build_tool_registry
# from app.llm import LLMClient


# # ---------------------------------------------------------
# # Configuration
# # ---------------------------------------------------------

# load_dotenv()

# MAX_CONCURRENT_TASKS = max(
#     1,
#     min(int(os.getenv("MAX_CONCURRENT_TASKS", "3")), 10),
# )

# MAX_BATCH_SIZE = max(
#     1,
#     min(int(os.getenv("MAX_BATCH_SIZE", "20")), 100),
# )

# _task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# # Local React development URL.
# # Add your deployed frontend URL to FRONTEND_ORIGINS on Render.
# frontend_origins = [
#     origin.strip()
#     for origin in os.getenv(
#         "FRONTEND_ORIGINS",
#         "http://localhost:5173,http://127.0.0.1:5173",
#     ).split(",")
#     if origin.strip()
# ]


# # ---------------------------------------------------------
# # Application lifecycle
# # ---------------------------------------------------------

# @asynccontextmanager
# async def lifespan(_app: FastAPI):
#     init_db()
#     yield


# app = FastAPI(
#     title="AgentOps",
#     version="1.2.0",
#     description="Multi-agent operations and observability platform",
#     lifespan=lifespan,
# )


# # ---------------------------------------------------------
# # CORS
# # ---------------------------------------------------------

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=frontend_origins,
#     allow_credentials=False,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ---------------------------------------------------------
# # Tool registry
# # ---------------------------------------------------------

# tool_registry = build_tool_registry()


# # ---------------------------------------------------------
# # Request models
# # ---------------------------------------------------------

# class TaskRequest(BaseModel):
#     description: str = Field(min_length=1, max_length=8_000)
#     repo: str | None = None

#     @field_validator("description")
#     @classmethod
#     def strip_description(cls, value: str) -> str:
#         value = value.strip()

#         if not value:
#             raise ValueError("description cannot be blank")

#         return value

#     @field_validator("repo")
#     @classmethod
#     def validate_repo(cls, value: str | None) -> str | None:
#         if value is None:
#             return None

#         value = value.strip()
#         parts = value.split("/")

#         if (
#             not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)
#             or any(
#                 part in {".", ".."} or part.startswith(".")
#                 for part in parts
#             )
#         ):
#             raise ValueError(
#                 "repo must be a GitHub owner/repository slug"
#             )

#         return value


# class BatchTaskRequest(BaseModel):
#     tasks: list[TaskRequest]


# class ApprovalRequest(BaseModel):
#     approved: bool


# # ---------------------------------------------------------
# # Shared task execution
# # ---------------------------------------------------------

# async def _run_single_task(
#     description: str,
#     repo: str | None,
#     llm: LLMClient | None = None,
# ) -> dict:
#     """
#     Executes one task through the AgentOps graph.

#     The semaphore limits concurrent graph executions to protect
#     the LLM provider's rate limits.
#     """

#     task_id = str(uuid.uuid4())

#     tracker = EvalTracker(task_id=task_id)
#     tracker.start_task(description)

#     async with _task_semaphore:
#         start = time.perf_counter()

#         graph = build_graph(
#             tracker=tracker,
#             llm=llm or LLMClient(),
#             tools=tool_registry,
#         )

#         initial_state = {
#             "task_id": task_id,
#             "description": description,
#             "repo": repo,
#             "status": "pending",
#             "trace": [],
#             "tool_calls": [],
#             "context_snippets": [],
#             "revision_count": 0,
#         }

#         try:
#             final_state = await graph.ainvoke(initial_state)

#         except Exception as exc:
#             tracker.update_task_status("failed")

#             return {
#                 "task_id": task_id,
#                 "description": description,
#                 "status": "failed",
#                 "error": str(exc),
#                 "wall_clock_ms": round(
#                     (time.perf_counter() - start) * 1000,
#                     1,
#                 ),
#             }

#         wall_clock_ms = round(
#             (time.perf_counter() - start) * 1000,
#             1,
#         )

#         if final_state.get("requires_human_approval"):
#             approval_store.add(
#                 task_id,
#                 final_state["proposed_action"],
#                 final_state["risk_score"],
#             )

#             tracker.update_task_status(
#                 "awaiting_approval",
#                 requires_human_approval=True,
#             )
#         else:
#             tracker.update_task_status("done")

#         return {
#             "task_id": task_id,
#             "description": description,
#             "status": final_state.get("status"),
#             "category": final_state.get("category"),
#             "priority": final_state.get("priority"),
#             "proposed_action": final_state.get("proposed_action"),
#             "risk_score": final_state.get("risk_score"),
#             "requires_human_approval": final_state.get(
#                 "requires_human_approval",
#                 False,
#             ),
#             "wall_clock_ms": wall_clock_ms,
#             "summary": tracker.task_summary(),
#         }


# # ---------------------------------------------------------
# # Health and metrics
# # ---------------------------------------------------------

# @app.get("/health")
# def health():
#     return {
#         "status": "ok",
#         "approval_store_backend": approval_store.backend,
#     }


# @app.get("/metrics")
# def metrics():
#     return aggregate_metrics()


# # ---------------------------------------------------------
# # React dashboard API
# # ---------------------------------------------------------

# @app.get("/dashboard/tasks")
# def get_dashboard_tasks(
#     limit: int = Query(default=100, ge=1, le=500),
# ):
#     """
#     Returns recent tasks from the EvalTracker database.
#     Used by the React Tasks and Overview pages.
#     """

#     return {
#         "items": dashboard_tasks(limit=limit),
#     }


# @app.get("/dashboard/traces")
# def get_dashboard_traces(
#     limit: int = Query(default=200, ge=1, le=1000),
# ):
#     """
#     Returns recent agent execution traces.
#     Used by the React Traces and Overview pages.
#     """

#     return {
#         "items": dashboard_query(limit=limit),
#     }


# # ---------------------------------------------------------
# # Single task execution with Server-Sent Events
# # ---------------------------------------------------------

# @app.post("/tasks")
# async def create_task(req: TaskRequest):
#     task_id = str(uuid.uuid4())

#     tracker = EvalTracker(task_id=task_id)
#     tracker.start_task(req.description)

#     async def event_stream():
#         graph = build_graph(
#             tracker=tracker,
#             llm=LLMClient(),
#             tools=tool_registry,
#         )

#         initial_state = {
#             "task_id": task_id,
#             "description": req.description,
#             "repo": req.repo,
#             "status": "pending",
#             "trace": [],
#             "tool_calls": [],
#             "context_snippets": [],
#             "revision_count": 0,
#         }

#         final_state = None

#         try:
#             async for event in graph.astream(initial_state):
#                 for node_name, node_output in event.items():
#                     final_state = node_output

#                     yield {
#                         "event": "node_complete",
#                         "data": json.dumps(
#                             {
#                                 "node": node_name,
#                                 "status": node_output.get("status"),
#                                 "trace_tail": (
#                                     node_output.get("trace", [])[-1]
#                                     if node_output.get("trace")
#                                     else None
#                                 ),
#                             }
#                         ),
#                     }

#             if (
#                 final_state
#                 and final_state.get("requires_human_approval")
#             ):
#                 approval_store.add(
#                     task_id,
#                     final_state["proposed_action"],
#                     final_state["risk_score"],
#                 )

#                 tracker.update_task_status(
#                     "awaiting_approval",
#                     requires_human_approval=True,
#                 )

#                 yield {
#                     "event": "awaiting_approval",
#                     "data": json.dumps(
#                         {
#                             "task_id": task_id,
#                             "action": final_state["proposed_action"],
#                             "risk_score": final_state["risk_score"],
#                         }
#                     ),
#                 }

#             else:
#                 tracker.update_task_status("done")

#                 yield {
#                     "event": "done",
#                     "data": json.dumps(tracker.task_summary()),
#                 }

#         except Exception as exc:
#             tracker.update_task_status("failed")

#             yield {
#                 "event": "error",
#                 "data": json.dumps(
#                     {
#                         "task_id": task_id,
#                         "error": str(exc),
#                     }
#                 ),
#             }

#     return EventSourceResponse(event_stream())


# # ---------------------------------------------------------
# # Batch task execution
# # ---------------------------------------------------------

# @app.post("/tasks/batch")
# async def create_tasks_batch(req: BatchTaskRequest):
#     """
#     Executes multiple tasks concurrently with a configured limit.
#     """

#     if not req.tasks:
#         raise HTTPException(
#             status_code=400,
#             detail="tasks list cannot be empty",
#         )

#     if len(req.tasks) > MAX_BATCH_SIZE:
#         raise HTTPException(
#             status_code=422,
#             detail=(
#                 f"tasks list cannot exceed "
#                 f"{MAX_BATCH_SIZE} items"
#             ),
#         )

#     start = time.perf_counter()

#     results = await asyncio.gather(
#         *[
#             _run_single_task(task.description, task.repo)
#             for task in req.tasks
#         ]
#     )

#     total_wall_clock_ms = round(
#         (time.perf_counter() - start) * 1000,
#         1,
#     )

#     return {
#         "batch_size": len(req.tasks),
#         "max_concurrent": MAX_CONCURRENT_TASKS,
#         "max_batch_size": MAX_BATCH_SIZE,
#         "total_wall_clock_ms": total_wall_clock_ms,
#         "results": results,
#     }


# # ---------------------------------------------------------
# # Human approval
# # ---------------------------------------------------------

# @app.post("/tasks/{task_id}/approve")
# def approve_task(
#     task_id: str,
#     req: ApprovalRequest,
# ):
#     resolved = approval_store.resolve(
#         task_id,
#         req.approved,
#     )

#     if resolved is None:
#         raise HTTPException(
#             status_code=404,
#             detail="No pending approval for this task_id",
#         )

#     tracker = EvalTracker(task_id=task_id)

#     tracker.update_task_status(
#         "done" if req.approved else "failed",
#         requires_human_approval=True,
#         approved=req.approved,
#     )

#     return {
#         "task_id": task_id,
#         "approved": req.approved,
#         "action": resolved["action"],
#         "executed": False,
#         "authorization_status": (
#             "approved" if req.approved else "rejected"
#         ),
#     }


# # ---------------------------------------------------------
# # Task details
# # ---------------------------------------------------------

# @app.get("/tasks/{task_id}")
# def get_task(task_id: str):
#     tracker = EvalTracker(task_id=task_id)
#     return tracker.task_summary()


# # ---------------------------------------------------------
# # Pending approvals
# # ---------------------------------------------------------

# @app.get("/tasks/pending/approvals")
# def list_pending_approvals():
#     return approval_store.pending()






















# from __future__ import annotations

# import asyncio
# import json
# import os
# import re
# import time
# import uuid
# from contextlib import asynccontextmanager

# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel, Field, field_validator
# from sse_starlette.sse import EventSourceResponse

# from app.approval import approval_store
# from app.eval_tracker import (
#     EvalTracker,
#     aggregate_metrics,
#     dashboard_query,
#     dashboard_tasks,
#     init_db,
# )
# from app.executor import execute_action
# from app.graph import build_graph, build_tool_registry
# from app.llm import LLMClient


# # ---------------------------------------------------------
# # Configuration
# # ---------------------------------------------------------

# load_dotenv()

# MAX_CONCURRENT_TASKS = max(
#     1,
#     min(int(os.getenv("MAX_CONCURRENT_TASKS", "3")), 10),
# )

# MAX_BATCH_SIZE = max(
#     1,
#     min(int(os.getenv("MAX_BATCH_SIZE", "20")), 100),
# )

# _task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# frontend_origins = [
#     origin.strip()
#     for origin in os.getenv(
#         "FRONTEND_ORIGINS",
#         "http://localhost:5173,http://127.0.0.1:5173",
#     ).split(",")
#     if origin.strip()
# ]


# # ---------------------------------------------------------
# # Application lifecycle
# # ---------------------------------------------------------

# @asynccontextmanager
# async def lifespan(_app: FastAPI):
#     init_db()
#     yield


# app = FastAPI(
#     title="AgentOps",
#     version="1.3.0",
#     description="Multi-agent operations and observability platform",
#     lifespan=lifespan,
# )


# # ---------------------------------------------------------
# # CORS
# # ---------------------------------------------------------

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=frontend_origins,
#     allow_credentials=False,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ---------------------------------------------------------
# # Tool registry
# # ---------------------------------------------------------

# tool_registry = build_tool_registry()


# # ---------------------------------------------------------
# # Request models
# # ---------------------------------------------------------

# class TaskRequest(BaseModel):
#     description: str = Field(min_length=1, max_length=8_000)
#     repo: str | None = None

#     @field_validator("description")
#     @classmethod
#     def strip_description(cls, value: str) -> str:
#         value = value.strip()

#         if not value:
#             raise ValueError("description cannot be blank")

#         return value

#     @field_validator("repo")
#     @classmethod
#     def validate_repo(cls, value: str | None) -> str | None:
#         if value is None:
#             return None

#         value = value.strip()
#         parts = value.split("/")

#         if (
#             not re.fullmatch(
#                 r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
#                 value,
#             )
#             or any(
#                 part in {".", ".."} or part.startswith(".")
#                 for part in parts
#             )
#         ):
#             raise ValueError(
#                 "repo must be a GitHub owner/repository slug"
#             )

#         return value


# class BatchTaskRequest(BaseModel):
#     tasks: list[TaskRequest]


# class ApprovalRequest(BaseModel):
#     approved: bool


# # ---------------------------------------------------------
# # Shared execution helper
# # ---------------------------------------------------------

# def _execute_final_action(
#     final_state: dict,
#     repo: str | None,
#     tracker: EvalTracker,
# ) -> dict:
#     """
#     Execute an action only after it has passed the Critic
#     and the graph has reached its completed state.
#     """

#     if not final_state.get("critic_passed"):
#         return {
#             "executed": False,
#             "success": False,
#             "execution_status": "blocked",
#             "message": "Action did not pass Critic validation.",
#         }

#     action = final_state.get("proposed_action")

#     if not isinstance(action, dict):
#         return {
#             "executed": False,
#             "success": False,
#             "execution_status": "invalid",
#             "message": "No valid proposed action was produced.",
#         }

#     return execute_action(
#         action=action,
#         repo=repo,
#         tools=tool_registry,
#         tracker=tracker,
#     )


# # ---------------------------------------------------------
# # Shared task execution
# # ---------------------------------------------------------

# async def _run_single_task(
#     description: str,
#     repo: str | None,
#     llm: LLMClient | None = None,
# ) -> dict:
#     """
#     Execute one task through the AgentOps graph.

#     Human approval is required before executing high-risk actions.
#     Auto-approved actions are sent to the Executor immediately.
#     """

#     task_id = str(uuid.uuid4())

#     tracker = EvalTracker(task_id=task_id)
#     tracker.start_task(description)

#     async with _task_semaphore:
#         start = time.perf_counter()

#         graph = build_graph(
#             tracker=tracker,
#             llm=llm or LLMClient(),
#             tools=tool_registry,
#         )

#         initial_state = {
#             "task_id": task_id,
#             "description": description,
#             "repo": repo,
#             "status": "pending",
#             "trace": [],
#             "tool_calls": [],
#             "context_snippets": [],
#             "revision_count": 0,
#         }

#         try:
#             final_state = await graph.ainvoke(initial_state)

#         except Exception as exc:
#             tracker.update_task_status("failed")

#             return {
#                 "task_id": task_id,
#                 "description": description,
#                 "status": "failed",
#                 "error": str(exc),
#                 "wall_clock_ms": round(
#                     (time.perf_counter() - start) * 1000,
#                     1,
#                 ),
#             }

#         execution_result = None
#         requires_approval = bool(
#             final_state.get("requires_human_approval")
#         )

#         if final_state.get("status") == "failed":
#             task_status = "failed"
#             tracker.update_task_status(task_status)

#         elif requires_approval:
#             approval_store.add(
#                 task_id,
#                 final_state["proposed_action"],
#                 final_state["risk_score"],
#             )

#             task_status = "awaiting_approval"

#             tracker.update_task_status(
#                 task_status,
#                 requires_human_approval=True,
#             )

#         elif final_state.get("status") == "done":
#             execution_result = _execute_final_action(
#                 final_state,
#                 repo,
#                 tracker,
#             )

#             task_status = (
#                 "done"
#                 if execution_result["success"]
#                 else "failed"
#             )

#             tracker.update_task_status(task_status)

#         else:
#             task_status = "failed"
#             tracker.update_task_status(task_status)

#         wall_clock_ms = round(
#             (time.perf_counter() - start) * 1000,
#             1,
#         )

#         return {
#             "task_id": task_id,
#             "description": description,
#             "status": task_status,
#             "category": final_state.get("category"),
#             "priority": final_state.get("priority"),
#             "proposed_action": final_state.get("proposed_action"),
#             "risk_score": final_state.get("risk_score"),
#             "requires_human_approval": requires_approval,
#             "execution_result": execution_result,
#             "wall_clock_ms": wall_clock_ms,
#             "summary": tracker.task_summary(),
#         }


# # ---------------------------------------------------------
# # Health and metrics
# # ---------------------------------------------------------

# @app.get("/health")
# def health():
#     return {
#         "status": "ok",
#         "approval_store_backend": approval_store.backend,
#     }


# @app.get("/metrics")
# def metrics():
#     return aggregate_metrics()


# # ---------------------------------------------------------
# # React dashboard API
# # ---------------------------------------------------------

# @app.get("/dashboard/tasks")
# def get_dashboard_tasks(
#     limit: int = Query(default=100, ge=1, le=500),
# ):
#     return {
#         "items": dashboard_tasks(limit=limit),
#     }


# @app.get("/dashboard/traces")
# def get_dashboard_traces(
#     limit: int = Query(default=200, ge=1, le=1000),
# ):
#     return {
#         "items": dashboard_query(limit=limit),
#     }


# # ---------------------------------------------------------
# # Single task execution with Server-Sent Events
# # ---------------------------------------------------------

# @app.post("/tasks")
# async def create_task(req: TaskRequest):
#     task_id = str(uuid.uuid4())

#     tracker = EvalTracker(task_id=task_id)
#     tracker.start_task(req.description)

#     async def event_stream():
#         async with _task_semaphore:
#             graph = build_graph(
#                 tracker=tracker,
#                 llm=LLMClient(),
#                 tools=tool_registry,
#             )

#             initial_state = {
#                 "task_id": task_id,
#                 "description": req.description,
#                 "repo": req.repo,
#                 "status": "pending",
#                 "trace": [],
#                 "tool_calls": [],
#                 "context_snippets": [],
#                 "revision_count": 0,
#             }

#             final_state = None

#             try:
#                 async for event in graph.astream(initial_state):
#                     for node_name, node_output in event.items():
#                         final_state = node_output

#                         yield {
#                             "event": "node_complete",
#                             "data": json.dumps({
#                                 "node": node_name,
#                                 "status": node_output.get("status"),
#                                 "trace_tail": (
#                                     node_output.get("trace", [])[-1]
#                                     if node_output.get("trace")
#                                     else None
#                                 ),
#                             }),
#                         }

#                 if final_state is None:
#                     raise RuntimeError(
#                         "Agent graph returned no final state."
#                     )

#                 if final_state.get("status") == "failed":
#                     tracker.update_task_status("failed")

#                     yield {
#                         "event": "error",
#                         "data": json.dumps({
#                             "task_id": task_id,
#                             "message": final_state.get(
#                                 "final_result",
#                                 "Agent workflow failed.",
#                             ),
#                         }),
#                     }
#                     return

#                 if final_state.get("requires_human_approval"):
#                     approval_store.add(
#                         task_id,
#                         final_state["proposed_action"],
#                         final_state["risk_score"],
#                     )

#                     tracker.update_task_status(
#                         "awaiting_approval",
#                         requires_human_approval=True,
#                     )

#                     yield {
#                         "event": "awaiting_approval",
#                         "data": json.dumps({
#                             "task_id": task_id,
#                             "action": final_state["proposed_action"],
#                             "risk_score": final_state["risk_score"],
#                         }),
#                     }
#                     return

#                 if final_state.get("status") != "done":
#                     tracker.update_task_status("failed")

#                     yield {
#                         "event": "error",
#                         "data": json.dumps({
#                             "task_id": task_id,
#                             "message": "Workflow did not reach a completed state.",
#                         }),
#                     }
#                     return

#                 execution_result = _execute_final_action(
#                     final_state,
#                     req.repo,
#                     tracker,
#                 )

#                 task_status = (
#                     "done"
#                     if execution_result["success"]
#                     else "failed"
#                 )

#                 tracker.update_task_status(task_status)

#                 yield {
#                     "event": "execution_complete",
#                     "data": json.dumps({
#                         "task_id": task_id,
#                         "execution_result": execution_result,
#                         "status": task_status,
#                     }),
#                 }

#                 yield {
#                     "event": "done" if task_status == "done" else "error",
#                     "data": json.dumps({
#                         "task_id": task_id,
#                         "status": task_status,
#                         "execution_result": execution_result,
#                         "summary": tracker.task_summary(),
#                     }),
#                 }

#             except Exception as exc:
#                 tracker.update_task_status("failed")

#                 yield {
#                     "event": "error",
#                     "data": json.dumps({
#                         "task_id": task_id,
#                         "error": str(exc),
#                     }),
#                 }

#     return EventSourceResponse(event_stream())


# # ---------------------------------------------------------
# # Batch task execution
# # ---------------------------------------------------------

# @app.post("/tasks/batch")
# async def create_tasks_batch(req: BatchTaskRequest):
#     if not req.tasks:
#         raise HTTPException(
#             status_code=400,
#             detail="tasks list cannot be empty",
#         )

#     if len(req.tasks) > MAX_BATCH_SIZE:
#         raise HTTPException(
#             status_code=422,
#             detail=(
#                 f"tasks list cannot exceed "
#                 f"{MAX_BATCH_SIZE} items"
#             ),
#         )

#     start = time.perf_counter()

#     results = await asyncio.gather(
#         *[
#             _run_single_task(task.description, task.repo)
#             for task in req.tasks
#         ]
#     )

#     total_wall_clock_ms = round(
#         (time.perf_counter() - start) * 1000,
#         1,
#     )

#     return {
#         "batch_size": len(req.tasks),
#         "max_concurrent": MAX_CONCURRENT_TASKS,
#         "max_batch_size": MAX_BATCH_SIZE,
#         "total_wall_clock_ms": total_wall_clock_ms,
#         "results": results,
#     }


# # ---------------------------------------------------------
# # Human approval
# # ---------------------------------------------------------

# @app.post("/tasks/{task_id}/approve")
# def approve_task(
#     task_id: str,
#     req: ApprovalRequest,
# ):
#     resolved = approval_store.resolve(
#         task_id,
#         req.approved,
#     )

#     if resolved is None:
#         raise HTTPException(
#             status_code=404,
#             detail="No pending approval for this task_id",
#         )

#     tracker = EvalTracker(task_id=task_id)
#     action = resolved["action"]

#     if not req.approved:
#         tracker.update_task_status(
#             "failed",
#             requires_human_approval=True,
#             approved=False,
#         )

#         return {
#             "task_id": task_id,
#             "approved": False,
#             "action": action,
#             "executed": False,
#             "execution_result": None,
#             "authorization_status": "rejected",
#             "status": "failed",
#         }

#     execution_result = execute_action(
#         action=action,
#         repo=action.get("repo"),
#         tools=tool_registry,
#         tracker=tracker,
#     )

#     task_status = (
#         "done"
#         if execution_result["success"]
#         else "failed"
#     )

#     tracker.update_task_status(
#         task_status,
#         requires_human_approval=True,
#         approved=True,
#     )

#     return {
#         "task_id": task_id,
#         "approved": True,
#         "action": action,
#         "executed": execution_result["executed"],
#         "execution_result": execution_result,
#         "authorization_status": "approved",
#         "status": task_status,
#     }


# # ---------------------------------------------------------
# # Task details
# # ---------------------------------------------------------

# @app.get("/tasks/{task_id}")
# def get_task(task_id: str):
#     tracker = EvalTracker(task_id=task_id)
#     return tracker.task_summary()


# # ---------------------------------------------------------
# # Pending approvals
# # ---------------------------------------------------------

# @app.get("/tasks/pending/approvals")
# def list_pending_approvals():
#     return approval_store.pending()





















from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from app.approval import approval_store
from app.eval_tracker import (
    EvalTracker,
    aggregate_metrics,
    dashboard_query,
    dashboard_tasks,
    init_db,
)
from app.executor import execute_action
from app.graph import build_graph, build_tool_registry
from app.llm import LLMClient


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv()

MAX_CONCURRENT_TASKS = max(
    1,
    min(int(os.getenv("MAX_CONCURRENT_TASKS", "3")), 10),
)

MAX_BATCH_SIZE = max(
    1,
    min(int(os.getenv("MAX_BATCH_SIZE", "20")), 100),
)

_task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]


# ---------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AgentOps",
    version="1.3.0",
    description="Multi-agent operations and observability platform",
    lifespan=lifespan,
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Tool registry
# ---------------------------------------------------------

tool_registry = build_tool_registry()


# ---------------------------------------------------------
# Request models
# ---------------------------------------------------------

class TaskRequest(BaseModel):
    description: str = Field(min_length=1, max_length=8_000)
    repo: str | None = None

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("description cannot be blank")

        return value

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        parts = value.split("/")

        if (
            not re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
                value,
            )
            or any(
                part in {".", ".."} or part.startswith(".")
                for part in parts
            )
        ):
            raise ValueError(
                "repo must be a GitHub owner/repository slug"
            )

        return value


class BatchTaskRequest(BaseModel):
    tasks: list[TaskRequest]


class ApprovalRequest(BaseModel):
    approved: bool


# ---------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------

def _prepare_approval_action(
    action: dict,
    repo: str | None,
) -> dict:
    """
    Preserve the original task repository in the action
    before storing it for human approval.
    """

    approval_action = dict(action)

    if repo and not approval_action.get("repo"):
        approval_action["repo"] = repo

    return approval_action


def _execute_final_action(
    final_state: dict,
    repo: str | None,
    tracker: EvalTracker,
) -> dict:
    """
    Execute an action only after Critic validation.

    Informational tasks complete successfully without invoking
    GitHub, Slack, or any external integration.
    """

    # Step 1: Verify Critic validation
    if not final_state.get("critic_passed"):
        return {
            "executed": False,
            "success": False,
            "execution_status": "blocked",
            "message": "Action did not pass Critic validation.",
        }

    # Step 2: Validate proposed action
    action = final_state.get("proposed_action")

    if not isinstance(action, dict):
        return {
            "executed": False,
            "success": False,
            "execution_status": "invalid",
            "message": "No valid proposed action was produced.",
        }

    # Step 3: Handle informational tasks
    if action.get("type") == "no_action":
        return {
            "executed": False,
            "success": True,
            "execution_status": "not_required",
            "message": (
                "Informational task completed. "
                "No external action was required."
            ),
        }

    # Step 4: Execute external actions
    return execute_action(
        action=action,
        repo=repo,
        tools=tool_registry,
        tracker=tracker,
    )


def _store_pending_approval(
    task_id: str,
    action: dict,
    risk_score: float,
    repo: str | None,
) -> dict:
    """
    Store an approval request with its original repository.
    """

    if not isinstance(action, dict):
        raise ValueError("Invalid proposed action.")

    approval_action = _prepare_approval_action(action, repo)

    approval_store.add(
        task_id,
        approval_action,
        risk_score,
    )

    return approval_action


# ---------------------------------------------------------
# Shared task execution
# ---------------------------------------------------------

async def _run_single_task(
    description: str,
    repo: str | None,
    llm: LLMClient | None = None,
) -> dict:

    task_id = str(uuid.uuid4())

    tracker = EvalTracker(task_id=task_id)
    tracker.start_task(description)

    async with _task_semaphore:
        start = time.perf_counter()

        graph = build_graph(
            tracker=tracker,
            llm=llm or LLMClient(),
            tools=tool_registry,
        )

        initial_state = {
            "task_id": task_id,
            "description": description,
            "repo": repo,
            "status": "pending",
            "trace": [],
            "tool_calls": [],
            "context_snippets": [],
            "revision_count": 0,
        }

        try:
            final_state = await graph.ainvoke(initial_state)

        except Exception as exc:
            tracker.update_task_status("failed")

            return {
                "task_id": task_id,
                "description": description,
                "status": "failed",
                "error": str(exc),
                "wall_clock_ms": round(
                    (time.perf_counter() - start) * 1000,
                    1,
                ),
            }

        execution_result = None

        requires_approval = bool(
            final_state.get("requires_human_approval")
        )

        if final_state.get("status") == "failed":

            task_status = "failed"
            tracker.update_task_status(task_status)

        elif requires_approval:

            action = final_state.get("proposed_action")

            if not isinstance(action, dict):
                task_status = "failed"
                tracker.update_task_status(task_status)

            else:
                _store_pending_approval(
                    task_id=task_id,
                    action=action,
                    risk_score=final_state["risk_score"],
                    repo=repo,
                )

                task_status = "awaiting_approval"

                tracker.update_task_status(
                    task_status,
                    requires_human_approval=True,
                )

        elif final_state.get("status") == "done":

            execution_result = _execute_final_action(
                final_state,
                repo,
                tracker,
            )

            task_status = (
                "done"
                if execution_result["success"]
                else "failed"
            )

            tracker.update_task_status(task_status)

        else:

            task_status = "failed"
            tracker.update_task_status(task_status)

        wall_clock_ms = round(
            (time.perf_counter() - start) * 1000,
            1,
        )

        return {
            "task_id": task_id,
            "description": description,
            "status": task_status,
            "category": final_state.get("category"),
            "priority": final_state.get("priority"),
            "proposed_action": final_state.get("proposed_action"),
            "risk_score": final_state.get("risk_score"),
            "requires_human_approval": requires_approval,
            "execution_result": execution_result,
            "wall_clock_ms": wall_clock_ms,
            "summary": tracker.task_summary(),
        }


# ---------------------------------------------------------
# Health and metrics
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "approval_store_backend": approval_store.backend,
    }


@app.get("/metrics")
def metrics():
    return aggregate_metrics()


# ---------------------------------------------------------
# React dashboard API
# ---------------------------------------------------------

@app.get("/dashboard/tasks")
def get_dashboard_tasks(
    limit: int = Query(default=100, ge=1, le=500),
):
    return {
        "items": dashboard_tasks(limit=limit),
    }


@app.get("/dashboard/traces")
def get_dashboard_traces(
    limit: int = Query(default=200, ge=1, le=1000),
):
    return {
        "items": dashboard_query(limit=limit),
    }


# ---------------------------------------------------------
# Single task execution with Server-Sent Events
# ---------------------------------------------------------

@app.post("/tasks")
async def create_task(req: TaskRequest):

    task_id = str(uuid.uuid4())

    tracker = EvalTracker(task_id=task_id)
    tracker.start_task(req.description)

    async def event_stream():

        async with _task_semaphore:

            graph = build_graph(
                tracker=tracker,
                llm=LLMClient(),
                tools=tool_registry,
            )

            initial_state = {
                "task_id": task_id,
                "description": req.description,
                "repo": req.repo,
                "status": "pending",
                "trace": [],
                "tool_calls": [],
                "context_snippets": [],
                "revision_count": 0,
            }

            final_state = None

            try:

                async for event in graph.astream(initial_state):

                    for node_name, node_output in event.items():

                        final_state = node_output

                        yield {
                            "event": "node_complete",
                            "data": json.dumps({
                                "node": node_name,
                                "status": node_output.get("status"),
                                "trace_tail": (
                                    node_output.get("trace", [])[-1]
                                    if node_output.get("trace")
                                    else None
                                ),
                            }),
                        }

                if final_state is None:
                    raise RuntimeError(
                        "Agent graph returned no final state."
                    )

                if final_state.get("status") == "failed":

                    tracker.update_task_status("failed")

                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "task_id": task_id,
                            "message": final_state.get(
                                "final_result",
                                "Agent workflow failed.",
                            ),
                        }),
                    }

                    return

                if final_state.get("requires_human_approval"):

                    action = final_state.get("proposed_action")

                    if not isinstance(action, dict):
                        tracker.update_task_status("failed")

                        yield {
                            "event": "error",
                            "data": json.dumps({
                                "task_id": task_id,
                                "message": "Invalid proposed action.",
                            }),
                        }

                        return

                    approval_action = _store_pending_approval(
                        task_id=task_id,
                        action=action,
                        risk_score=final_state["risk_score"],
                        repo=req.repo,
                    )

                    tracker.update_task_status(
                        "awaiting_approval",
                        requires_human_approval=True,
                    )

                    yield {
                        "event": "awaiting_approval",
                        "data": json.dumps({
                            "task_id": task_id,
                            "action": approval_action,
                            "risk_score": final_state["risk_score"],
                        }),
                    }

                    return

                if final_state.get("status") != "done":

                    tracker.update_task_status("failed")

                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "task_id": task_id,
                            "message": (
                                "Workflow did not reach a completed state."
                            ),
                        }),
                    }

                    return

                execution_result = _execute_final_action(
                    final_state,
                    req.repo,
                    tracker,
                )

                task_status = (
                    "done"
                    if execution_result["success"]
                    else "failed"
                )

                tracker.update_task_status(task_status)

                yield {
                    "event": "execution_complete",
                    "data": json.dumps({
                        "task_id": task_id,
                        "execution_result": execution_result,
                        "status": task_status,
                    }),
                }

                yield {
                    "event": (
                        "done"
                        if task_status == "done"
                        else "error"
                    ),
                    "data": json.dumps({
                        "task_id": task_id,
                        "status": task_status,
                        "execution_result": execution_result,
                        "summary": tracker.task_summary(),
                    }),
                }

            except Exception as exc:

                tracker.update_task_status("failed")

                yield {
                    "event": "error",
                    "data": json.dumps({
                        "task_id": task_id,
                        "error": str(exc),
                    }),
                }

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------
# Batch task execution
# ---------------------------------------------------------

@app.post("/tasks/batch")
async def create_tasks_batch(req: BatchTaskRequest):

    if not req.tasks:
        raise HTTPException(
            status_code=400,
            detail="tasks list cannot be empty",
        )

    if len(req.tasks) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"tasks list cannot exceed "
                f"{MAX_BATCH_SIZE} items"
            ),
        )

    start = time.perf_counter()

    results = await asyncio.gather(
        *[
            _run_single_task(
                task.description,
                task.repo,
            )
            for task in req.tasks
        ]
    )

    total_wall_clock_ms = round(
        (time.perf_counter() - start) * 1000,
        1,
    )

    return {
        "batch_size": len(req.tasks),
        "max_concurrent": MAX_CONCURRENT_TASKS,
        "max_batch_size": MAX_BATCH_SIZE,
        "total_wall_clock_ms": total_wall_clock_ms,
        "results": results,
    }


# ---------------------------------------------------------
# Human approval
# ---------------------------------------------------------

@app.post("/tasks/{task_id}/approve")
def approve_task(
    task_id: str,
    req: ApprovalRequest,
):

    resolved = approval_store.resolve(
        task_id,
        req.approved,
    )

    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail="No pending approval for this task_id",
        )

    tracker = EvalTracker(task_id=task_id)

    action = resolved.get("action")

    if not isinstance(action, dict):
        raise HTTPException(
            status_code=400,
            detail="Stored approval action is invalid.",
        )

    if not req.approved:

        tracker.update_task_status(
            "failed",
            requires_human_approval=True,
            approved=False,
        )

        return {
            "task_id": task_id,
            "approved": False,
            "action": action,
            "executed": False,
            "execution_result": None,
            "authorization_status": "rejected",
            "status": "failed",
        }

    # Repository is now preserved when the action
    # was originally placed in the approval store.
    execution_result = execute_action(
        action=action,
        repo=action.get("repo"),
        tools=tool_registry,
        tracker=tracker,
    )

    task_status = (
        "done"
        if execution_result["success"]
        else "failed"
    )

    tracker.update_task_status(
        task_status,
        requires_human_approval=True,
        approved=True,
    )

    return {
        "task_id": task_id,
        "approved": True,
        "action": action,
        "executed": execution_result["executed"],
        "execution_result": execution_result,
        "authorization_status": "approved",
        "status": task_status,
    }


# ---------------------------------------------------------
# Task details
# ---------------------------------------------------------

@app.get("/tasks/{task_id}")
def get_task(task_id: str):

    tracker = EvalTracker(task_id=task_id)

    return tracker.task_summary()


# ---------------------------------------------------------
# Pending approvals
# ---------------------------------------------------------

@app.get("/tasks/pending/approvals")
def list_pending_approvals():

    return approval_store.pending()
