from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class SignupViewTest(TestCase):

    def test_get_renders_signup_form(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup.html")

    def test_valid_post_creates_user_and_redirects(self):
        response = self.client.post(reverse("signup"), {
            "username": "newuser",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_mismatched_passwords_shows_error(self):
        response = self.client.post(reverse("signup"), {
            "username": "newuser2",
            "password1": "StrongPass123!",
            "password2": "DifferentPass456!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("password2", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="newuser2").exists())

    def test_duplicate_username_shows_error(self):
        User.objects.create_user(username="existinguser", password="pass")
        response = self.client.post(reverse("signup"), {
            "username": "existinguser",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
