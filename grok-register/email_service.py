"""
邮箱服务类（改为 GPTMail）
保持接口不变：
- create_email() -> (token_like, email)
- fetch_first_email(token_like) -> str | None
"""

import re
import urllib.parse
from typing import Any, Dict, List, Optional

from curl_cffi import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"


class GPTMailClient:
    """与 openai_register.py 一致的 GPTMail 访问方式（含首页初始化 + 表单接口抓取）"""

    def __init__(self, proxies: Any = None):
        self.base_url = "https://mail.chatgpt.org.uk"
        self.session = requests.Session(proxies=proxies, impersonate="chrome")
        self.session.headers.update(
            {
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": f"{self.base_url}/",
            }
        )

    def _init_browser_session(self):
        """先访问首页，提取 gm_sid / x-inbox-token（与 openai_register.py 一致）"""
        try:
            resp = self.session.get(self.base_url, timeout=15)

            gm_sid = self.session.cookies.get("gm_sid")
            if gm_sid:
                self.session.headers.update({"Cookie": f"gm_sid={gm_sid}"})

            token_match = re.search(r"(eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)", resp.text)
            if token_match:
                self.session.headers.update({"x-inbox-token": token_match.group(1)})
        except Exception:
            pass

    def generate_email(self) -> str:
        self._init_browser_session()
        resp = self.session.get(f"{self.base_url}/api/generate-email", timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"GPTMail 生成失败: {resp.status_code}")

        data = resp.json()
        email = str(((data.get("data") or {}).get("email") or "")).strip()
        token = str(((data.get("auth") or {}).get("token") or "")).strip()
        if token:
            self.session.headers.update({"x-inbox-token": token})
        if not email:
            raise RuntimeError("GPTMail 返回邮箱为空")
        return email

    def list_emails(self, email: str) -> List[Dict[str, Any]]:
        encoded_email = urllib.parse.quote(email)
        url = f"{self.base_url}/api/emails?email={encoded_email}"
        resp = self.session.get(url, timeout=15)
        if resp.status_code == 200:
            return ((resp.json() or {}).get("data") or {}).get("emails") or []
        return []


class EmailService:
    """使用 GPTMail 的邮箱服务（对外接口与旧实现兼容）"""

    def __init__(self, proxies: Any = None):
        self.proxies = proxies

    def create_email(self):
        """创建 GPTMail 邮箱，返回 (token_like, email)"""
        try:
            client = GPTMailClient(self.proxies)
            email = client.generate_email()
            # 兼容旧调用方：第一个返回值依旧命名为 jwt/token，这里改为上下文对象
            token_like = {"client": client, "email": email}
            return token_like, email
        except Exception as e:
            print(f"[Error] 请求 GPTMail API 出错: {e}")
            return None, None

    def fetch_first_email(self, token_like):
        """
        获取第一封邮件摘要内容。
        兼容 grok.py 现有正则：返回文本内附带一段 >subject<，
        若 subject 中含 ABC-DEF 可被原逻辑直接匹配。
        """
        try:
            if not isinstance(token_like, dict):
                return None

            client: Optional[GPTMailClient] = token_like.get("client")
            email = str(token_like.get("email") or "").strip()
            if not client or not email:
                return None

            emails = client.list_emails(email)
            if not emails:
                return None

            first = emails[0] or {}
            subject = str(first.get("subject") or "")

            # 兼容两种返回结构：
            # 1) from: {name,address}, text, html
            # 2) from_address, content, html_content（你给的示例）
            from_name = str(((first.get("from") or {}).get("name") or ""))
            from_email = str(((first.get("from") or {}).get("address") or first.get("from_address") or ""))
            body_text = str(first.get("text") or first.get("content") or "")
            body_html = str(first.get("html") or first.get("html_content") or "")

            # 保留 >...< 包裹 + 原始 html，供上层正则提取验证码
            return "\n".join([f">{subject}<", subject, from_name, from_email, body_text, body_html])
        except Exception as e:
            print(f"获取邮件失败: {e}")
            return None
