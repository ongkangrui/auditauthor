import os

import httpx
import streamlit as st

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
st.set_page_config(page_title="AuditAuthor", page_icon="📋", layout="wide")


def api(method, path, **kwargs):
    try:
        response = httpx.request(method, BASE_URL + path, timeout=90, **kwargs)
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as exc:
        try:
            message = exc.response.json().get("detail", "Request failed")
        except ValueError:
            message = "Backend request failed."
        st.error(str(message))
    except httpx.RequestError:
        st.error("Cannot reach the backend. Check that the backend container is running.")
    st.stop()


st.title("AuditAuthor")
st.caption("Review IT-control observations across AGO reports, with traceable source evidence.")
with st.sidebar:
    st.header("Reports")
    uploaded = st.file_uploader("Upload annual reports", type=["pdf"], accept_multiple_files=True)
    if st.button("Import uploaded reports", disabled=not uploaded):
        for file in uploaded:
            api("POST", "/reports", files={"file": (file.name, file.getvalue(), "application/pdf")})
        st.success("Reports imported.")
    reports = api("GET", "/reports").json()
    report_names = {r["id"]: r["name"] for r in reports}
    selected = st.multiselect(
        "Reports to analyse", list(report_names), format_func=report_names.get
    )
    if st.button("Analyse selected reports", disabled=not selected, type="primary"):
        job = api("POST", "/analyses", json={"report_ids": selected}).json()
        st.session_state["analysis_id"] = job["id"]
        st.rerun()
    jobs = api("GET", "/analyses").json()
    ids = [j["id"] for j in jobs]
    if not ids:
        st.info("Import reports and start an analysis.")
        st.stop()
    if st.session_state.get("analysis_id") not in ids:
        st.session_state["analysis_id"] = ids[0]
    labels = {j["id"]: f"{j['created_at'][:16]} UTC · {j['status']} · {j['id'][:6]}" for j in jobs}
    job_id = st.selectbox("Saved analyses", ids, key="analysis_id", format_func=labels.get)


@st.fragment(run_every="3s")
def progress(job_id):
    job = api("GET", f"/analyses/{job_id}").json()
    coverage = job.get("coverage", {})
    st.subheader(f"Analysis: {job['status']}")
    total = coverage.get("total_chunks", 0)
    done = coverage.get("completed_chunks", 0)
    st.progress(done / total if total else 0, text=f"{done}/{total} chunks completed")
    st.caption(
        f"Model: {job['model']} · Prompt {job['prompt_version']} · Schema {job['schema_version']}"
    )
    if job["status"] in ("partial", "failed", "interrupted"):
        st.warning(
            "Coverage is incomplete. Results do not represent a complete review of the selected reports."
        )
        if st.button("Retry failed work"):
            api("POST", f"/analyses/{job_id}/retry")
            st.rerun()
    if job["errors"] or coverage.get("page_warnings"):
        with st.expander("Processing errors and page coverage"):
            st.json({"errors": job["errors"], "page_warnings": coverage.get("page_warnings", [])})
    if st.button("Refresh results"):
        st.rerun()
    previous = st.session_state.get(f"status_{job_id}")
    st.session_state[f"status_{job_id}"] = job["status"]
    if previous in ("queued", "running") and previous != job["status"]:
        st.rerun()
    return job


job = progress(job_id)
findings = api("GET", f"/analyses/{job_id}/findings").json()
insights = api("GET", f"/analyses/{job_id}/insights").json()
overview, observations, sources = st.tabs(
    ["Cross-report insights", "Observations", "Source evidence"]
)
with overview:
    st.caption(
        "Recurring means supported in at least two distinct reports. Counts do not establish a worsening trend."
    )
    if not insights:
        st.info("No consolidated insights available yet. Check status and processing errors.")
    for insight in insights:
        with st.expander(
            f"{'Recurring · ' if insight['recurring'] else ''}{insight['weakness']}", expanded=True
        ):
            st.write(insight["audit_implication"])
            st.caption(
                f"{insight['theme']} · {insight['report_count']} reports · {insight['agency_count']} known agencies"
            )
            if insight["repeated_entities"]:
                st.write("Repeated agency/system findings:", insight["repeated_entities"])
            st.write("Supporting observation IDs:", insight["observation_ids"])
with observations:
    theme = st.selectbox("Theme", ["All"] + sorted({f["theme"] for f in findings}))
    agency = st.selectbox(
        "Agency", ["All"] + sorted({f["agency"] for f in findings if f["agency"]})
    )
    report_filter = st.selectbox(
        "Report", ["All"] + job["report_ids"], format_func=lambda i: report_names.get(i, i)
    )
    visible = [
        f
        for f in findings
        if (theme == "All" or f["theme"] == theme)
        and (agency == "All" or f["agency"] == agency)
        and (report_filter == "All" or f["report_id"] == report_filter)
    ]
    st.dataframe(
        [
            {
                k: f[k]
                for k in (
                    "id",
                    "title",
                    "agency",
                    "system",
                    "theme",
                    "weakness",
                    "risk",
                    "reported_remediation",
                )
            }
            for f in visible
        ],
        width="stretch",
        hide_index=True,
    )
    for format in ("csv", "json"):
        st.download_button(
            f"Export {format.upper()}",
            api("GET", f"/analyses/{job_id}/export", params={"format": format}).content,
            file_name=f"audit-{job_id}.{format}",
            mime="text/csv" if format == "csv" else "application/json",
        )
with sources:
    st.caption(
        "Excerpts are text-verified. Review the original context to assess whether each interpretation is supported."
    )
    if findings:
        finding = st.selectbox(
            "Observation", findings, format_func=lambda f: f"{f['id']} · {f['title']}"
        )
        st.write(finding["weakness"])
        st.write(
            f"Agency: {finding['agency'] or 'Not stated'} · System: {finding['system'] or 'Not stated'}"
        )
        for evidence in finding["evidence"]:
            st.markdown(f"**Physical PDF page {evidence['page']}**")
            st.text(evidence["excerpt"])
        st.caption(
            f"Original report: {report_names[finding['report_id']]} — navigate to the physical page above."
        )
        pdf = api("GET", f"/reports/{finding['report_id']}/file").content
        st.pdf(pdf, height=700)
        st.download_button(
            "Download original PDF",
            pdf,
            file_name=report_names[finding["report_id"]],
            mime="application/pdf",
        )
