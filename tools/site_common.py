"""Constants and helpers shared by the static-site generators (build_blog, build_re_devlog, build_player_hub, build_press, blog_dev)."""
import html
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "web")
SITE = "https://nfsu.cc"
REPO = "https://github.com/Caliko06/need-for-speed-underground-browser"
LANGS = ("en", "es")
e = html.escape
ORG = {
    "@type": "Organization",
    "name": "NFS Underground Web",
    "url": SITE + "/",
    "logo": {"@type": "ImageObject", "url": SITE + "/icon-512.png"},
}


def url(lang, name):
    return "%s/blog/%s/%s.html" % (SITE, lang, name)
