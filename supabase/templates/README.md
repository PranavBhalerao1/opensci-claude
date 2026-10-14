# Auth email templates

OpenScientist-branded versions of the emails Supabase Auth sends. Paste each file into
Supabase: Authentication > Emails > Templates, and set the subject shown here.

| Supabase template | File | Subject |
|---|---|---|
| Confirm signup | `confirm-signup.html` | Confirm your email · OpenScientist |
| Reset password | `reset-password.html` | Reset your password · OpenScientist |
| Magic link | `magic-link.html` | Your sign-in link · OpenScientist |
| Change email address | `change-email.html` | Confirm your new email · OpenScientist |
| Invite user | `invite.html` | You're invited to OpenScientist |

Styles are inline because most email clients drop `<style>` blocks. Newsreader, Inter and
IBM Plex Mono load where the client allows web fonts (Apple Mail, iOS); Gmail and Outlook
fall back to Georgia, Helvetica and Menlo.
