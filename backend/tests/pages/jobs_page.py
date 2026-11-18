from playwright.sync_api import Page, expect


class JobsPage:
    def __init__(self, page: Page):
        self.page = page

    def open(self):
        self.page.get_by_role("button", name="HireTest Jobs", exact=True).click()
        self.page.get_by_role("heading", name="HireTest Jobs.").wait_for()

    def create_job(self, title: str, company: str, location: str, description: str):
        self.page.get_by_label("Job title").fill(title)
        self.page.get_by_label("Company").fill(company)
        self.page.get_by_label("Location").fill(location)
        self.page.get_by_label("Description").fill(description)
        self.page.get_by_role("button", name="Create job posting").click()
        expect(self.page.get_by_role("heading", name=title)).to_be_visible()

    def apply_for(self, title: str):
        card = self.page.locator(".job-card").filter(has=self.page.get_by_role("heading", name=title))
        card.get_by_role("button", name="Apply").click()

    def review_applicants(self, title: str, student_name: str, status: str):
        card = self.page.locator(".job-card").filter(has=self.page.get_by_role("heading", name=title))
        card.get_by_role("button", name="View applicants").click()
        expect(self.page.get_by_role("heading", name=f"Applicants for {title}")).to_be_visible()
        expect(self.page.get_by_text(student_name)).to_be_visible()
        self.page.get_by_label(f"Status for {student_name}").select_option(status)
        expect(self.page.get_by_label(f"Status for {student_name}")).to_have_value(status)
