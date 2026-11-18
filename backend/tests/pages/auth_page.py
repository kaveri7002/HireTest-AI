from playwright.sync_api import Page


class AuthPage:
    def __init__(self, page: Page):
        self.page = page

    def register(self, name: str, email: str, password: str, role: str):
        self.page.get_by_role("button", name="Create account").first.click()
        self.page.get_by_label("Your name").fill(name)
        self.page.get_by_label("Email address").fill(email)
        self.page.get_by_label("Password").fill(password)
        self.page.get_by_label("Account type").select_option(role)
        self.page.get_by_role("button", name="Create account").last.click()
        self.page.get_by_role("navigation", name="Main navigation").wait_for()

    def sign_out(self):
        self.page.get_by_role("button", name="Sign out").click()
        self.page.get_by_label("Email address").wait_for()

    def sign_in(self, email: str, password: str):
        self.page.get_by_role("button", name="Sign in").first.click()
        self.page.get_by_label("Email address").fill(email)
        self.page.get_by_label("Password").fill(password)
        self.page.get_by_role("button", name="Sign in").last.click()
        self.page.get_by_role("navigation", name="Main navigation").wait_for()
