"""稿件编排。"""

from __future__ import annotations



from typing import TYPE_CHECKING, Any



from core import manuscript

from core import profiles



if TYPE_CHECKING:

    from app.context import AppContext





def list_all(*, book_id: str | None = None) -> dict:

    return {"ok": True, "manuscripts": manuscript.list_manuscripts(book_id=book_id)}





def get_one(manuscript_id: str) -> dict:

    doc = manuscript.load_manuscript(manuscript_id)

    if not doc:

        return {"ok": False, "error": "稿件不存在"}

    return {"ok": True, "manuscript": doc}





def create_from_active_book(ctx: AppContext, *, title: str = "") -> dict:

    import json



    from core import project_lifecycle



    book_dir = ctx.store.paths.data_dir

    project_path = book_dir / "project.json"

    project_title = ""

    project_doc: dict = {}

    if project_path.is_file():

        try:

            raw = json.loads(project_path.read_text(encoding="utf-8"))

            if isinstance(raw, dict):

                project_doc = raw

                project_title = str(raw.get("title") or "").strip()

        except (json.JSONDecodeError, OSError):

            pass

    from core.data import book_context



    book_id = book_context.get_context().book_id

    ms_title = (title or project_title or "未命名稿件").strip()

    created = manuscript.create_from_book(

        book_id=book_id,

        title=ms_title,

        snapshot_note="从当前书交接为稿件",

    )

    if created.get("ok"):

        ms_id = created["manuscript"]["id"]

        project_lifecycle.update_lifecycle(book_dir, {"manuscript_id": ms_id})

    return created





def patch(ctx: AppContext, manuscript_id: str, fields: dict[str, Any]) -> dict:

    if "submission" in fields and isinstance(fields["submission"], dict):

        sub = dict(fields["submission"])

        if not sub.get("platform_profile") and sub.get("target"):

            project_path = ctx.store.paths.data_dir / "project.json"

            book_type = "short"

            platform = "tomato"

            if project_path.is_file():

                try:

                    import json



                    raw = json.loads(project_path.read_text(encoding="utf-8"))

                    if isinstance(raw, dict):

                        book_type = str(raw.get("type") or book_type)

                        platform = str(raw.get("platform") or platform)

                except (json.JSONDecodeError, OSError):

                    pass

            sub.setdefault(

                "platform_profile",

                profiles.resolve_default_profile_id(

                    book_type=book_type,

                    platform=platform,

                    submission_target=str(sub.get("target") or "text_editor"),

                ),

            )

            fields = {**fields, "submission": sub}



    result = manuscript.update_manuscript(manuscript_id, fields)

    if not result.get("ok"):

        return result



    diagnosis_id = None

    if "submission" in fields and isinstance(fields["submission"], dict):

        sub = fields["submission"]

        doc = result.get("manuscript") or {}

        from core import taste as taste_store



        taste_store.record_submission_event(

            book_id=str(doc.get("book_id") or ""),

            manuscript_id=manuscript_id,

            result=str(sub.get("result") or ""),

            reject_tags=sub.get("reject_tags"),

            reject_reason=str(sub.get("reject_reason") or ""),

        )

        result_val = str(sub.get("result") or "").strip().lower()

        if result_val in ("rejected", "reject", "拒稿", "failed"):

            from core import diagnosis_store

            from core.data import book_context



            submissions = doc.get("submissions") or []

            last_sub = submissions[-1] if submissions else {}

            diag = diagnosis_store.create_pending(

                ctx.store.paths.data_dir,

                book_id=book_context.get_context().book_id,

                trigger="rejection",

                trigger_ref={"type": "submission", "id": last_sub.get("id", "")},

                issue_tags=sub.get("reject_tags") or [],

                analysis=str(sub.get("reject_reason") or "投递拒稿")[:2000],

                patch={},

            )

            diagnosis_id = diag.get("id")

            result["diagnosis_id"] = diagnosis_id

            result["next_action"] = "POST /api/prompts/diagnose 或 PATCH diagnosis 归因"



    return result





def transition(manuscript_id: str, new_state: str) -> dict:

    return manuscript.transition_state(manuscript_id, new_state)

