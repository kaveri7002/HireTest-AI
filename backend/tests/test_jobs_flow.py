from datetime import datetime, timedelta

from playwright.sync_api import expect

from backend.tests.pages.auth_page import AuthPage
from backend.tests.pages.jobs_page import JobsPage


def test_recruiter_posts_and_student_applies_to_a_job(page, live_server):
    page.goto(live_server)
    auth = AuthPage(page)
    jobs = JobsPage(page)

    auth.register("Portal Recruiter", "recruiter@e2e.test", "StrongPassword123", "recruiter")
    jobs.open()
    jobs.create_job(
        "Playwright QA Engineer",
        "HireTest Demo",
        "Remote",
        "Validate job portal workflows with browser tests.",
        "Internship",
    )
    expect(page.get_by_role("status")).to_contain_text("Job posted successfully.")

    auth.sign_out()
    auth.register("Portal Student", "student@e2e.test", "StrongPassword123", "student")
    jobs.open()
    demo_job = page.locator(".job-card").filter(has_text="DEMO ONLY").first
    expect(demo_job.get_by_role("button", name="Sample only")).to_be_disabled()
    page.get_by_label("Filter by job type").select_option(label="Full time")
    expect(page.get_by_role("heading", name="Playwright QA Engineer")).not_to_be_visible()
    page.get_by_label("Filter by job type").select_option(label="Internship")
    job_card = page.locator(".job-card").filter(has=page.get_by_role("heading", name="Playwright QA Engineer"))
    expect(job_card).to_be_visible()
    job_card.get_by_role("button", name="Save Playwright QA Engineer").click()
    page.get_by_role("button", name="Saved (1)").click()
    expect(page.get_by_role("heading", name="Saved jobs")).to_be_visible()
    expect(job_card).to_be_visible()
    page.get_by_role("button", name="Saved (1)").click()

    page.get_by_role("button", name="Test cases", exact=True).click()
    page.get_by_role("button", name="Approve").first.click()
    expect(page.get_by_role("button", name="Approved").first).to_be_visible()
    page.get_by_role("button", name="Edit Matching search returns results").click()
    page.get_by_label("Title").fill("Updated search example")
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_role("heading", name="Updated search example")).to_be_visible()

    jobs.open()
    jobs.apply_for("Playwright QA Engineer")
    application_form = page.locator(".application-form")
    application_form.get_by_label("Phone (optional)").fill("+1 555 123 4567")
    application_form.get_by_label("Skills (comma-separated)").fill("Python, Playwright")
    application_form.get_by_label("Resume link (optional)").fill("https://example.test/portal-student-resume")
    application_form.get_by_label("Short note (optional)").fill("I enjoy testing browser workflows.")
    page.get_by_role("button", name="Submit application").click()
    expect(page.get_by_role("status")).to_contain_text("Your application was submitted.")

    expect(page.get_by_role("button", name="Applied · submitted")).to_be_disabled()
    expect(page.get_by_role("heading", name="My applications")).to_be_visible()
    auth.sign_out()
    auth.sign_in("recruiter@e2e.test", "StrongPassword123")
    jobs.open()
    jobs.review_applicants("Playwright QA Engineer", "Portal Student", "shortlisted")
    expect(page.get_by_text("+1 555 123 4567")).to_be_visible()
    expect(page.get_by_text("Python, Playwright")).to_be_visible()
    expect(page.get_by_text("I enjoy testing browser workflows.")).to_be_visible()
    page.get_by_role("button", name="Schedule interview").click()
    scheduled_at = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    page.locator('input[name="scheduledAt"]').fill(scheduled_at)
    page.get_by_label("Meeting link (optional)").fill("https://meet.example.test/hiretest")
    page.get_by_role("button", name="Send interview invite").click()
    expect(page.get_by_role("status")).to_contain_text("Interview scheduled.")

    auth.sign_out()
    auth.sign_in("student@e2e.test", "StrongPassword123")
    jobs.open()
    expect(page.get_by_role("link", name="Join interview")).to_be_visible()
    page.get_by_role("button", name="Notifications").click()
    expect(page.get_by_text("Interview scheduled", exact=True)).to_be_visible()
