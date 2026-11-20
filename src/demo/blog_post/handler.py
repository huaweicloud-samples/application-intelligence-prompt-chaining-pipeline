"""博客长文生成 demo：函数入口。"""
from demo._handler import make_handler
from demo.blog_post.flow import run_flow

handler = make_handler(run_flow)
