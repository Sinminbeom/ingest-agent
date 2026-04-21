import time

from logger.app_logger import AppLogger

from src.app.ingest_agent import IngestAgent
from src.config.project_config import ProjectConfig


def main():
    ProjectConfig.set_config("../../conf/application.conf")
    AppLogger.set_config("../../conf/logging.conf", ProjectConfig.instance().project_name)

    ingest_agent = IngestAgent()
    ingest_agent.start()

    ############################################################################
    member_id = "019b6824-397b-71dd-8f50-b52c7346cfa1"
    setting_config(member_id)

    ############################################################################
    batch_id = "019b6884-070d-7d6f-8431-abc17778d72b"

    ingest_agent.upload(batch_id)

    ############################################################################

    while True:
        time.sleep(1)
    pass

def setting_config(member_id: str):
    member_id_key = (ProjectConfig.E_CATE_TYPE.COMMON, ProjectConfig.E_CATE_ELE_COMMON.MEMBER_ID.lower())
    member_id_value = member_id
    ProjectConfig.instance().config[member_id_key] = member_id_value
    ProjectConfig.instance().member_id = member_id_value
    pass

if __name__ == "__main__":
    main()