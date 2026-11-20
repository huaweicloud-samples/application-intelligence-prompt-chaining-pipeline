from demo._handler import make_handler
from demo.most_popular_repo.flow import run_flow

handler = make_handler(run_flow)
