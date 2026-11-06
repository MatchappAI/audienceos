"""Remove an audience's files on disk (uploads, extracted media, generated reports) when the audience is deleted.
Call audience_dirs() BEFORE deleting the rows (the ids come from the database), then purge() after."""
import shutil

from . import config, db


def audience_dirs(audience_ids: list[str]) -> list:
    dirs = []
    for aid in audience_ids:
        dirs.append(config.UPLOADS_DIR / aid)
        dirs += [config.MEDIA_DIR / r["id"] for r in db.all_("SELECT id FROM sources WHERE audience_id=?", (aid,))]
        dirs += [config.REPORTS_DIR / r["id"] for r in db.all_("SELECT id FROM reports WHERE audience_id=?", (aid,))]
    return dirs


def purge(dirs: list) -> None:
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
