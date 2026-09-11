from app.services.content import sanitize_html


def test_sanitizer_removes_executable_and_unsafe_markup():
    raw = '<p onclick="steal()">Safe</p><script>alert(1)</script><iframe src="https://evil.example"></iframe><style>body{display:none}</style><a href="javascript:alert(1)">bad</a>'
    assert sanitize_html(raw) == "<p>Safe</p><a>bad</a>"


def test_sanitizer_preserves_safe_news_markup():
    raw = '<h2>News</h2><p><strong>Verified</strong> copy <a href="https://newsforge.test">source</a></p><ul><li>One</li></ul><img src="https://newsforge.test/photo.jpg" alt="News photo">'
    assert sanitize_html(raw) == raw
