import resend

resend.api_key = "re_8Th4yY1r_2TNJt2ktWhwsEVra2h55t1W5"

params: resend.Emails.SendParams = {
  "from": "Acme <error@burgerbin.top>",
  "to": ["1932395134@qq.com"],
  "subject": "hello world",
  "html": "<p>it works!</p>"
}

email = resend.Emails.send(params)
print(email)
