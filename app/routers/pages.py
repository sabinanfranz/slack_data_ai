from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request):
    return templates.TemplateResponse(
        "channels.html",
        {"request": request, "title": "Channels"},
    )


@router.get("/threads", response_class=HTMLResponse)
def threads_page(request: Request):
    return templates.TemplateResponse(
        "threads.html",
        {"request": request, "title": "Threads"},
    )


@router.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    return templates.TemplateResponse(
        "stats.html",
        {"request": request, "title": "Stats"},
    )


@router.get("/thread-reports", response_class=HTMLResponse)
def thread_reports_page(request: Request):
    return templates.TemplateResponse(
        "thread_reports.html",
        {"request": request, "title": "Thread Reports"},
    )
