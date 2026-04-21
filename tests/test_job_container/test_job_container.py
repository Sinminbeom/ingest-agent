from src.job_container.request_container import RequestContainer
from src.utils.protocol_utils import ProtocolUtils


def test_job_container():
    req = RequestContainer()

    seq_id = ProtocolUtils.instance().get_sequence_id_now()

    req.add_markers(
        seq_id=seq_id,
        batch_id="B1",
        project_id="P1",
        sample_id="S1",
        markers=["step1", "step2", "step3"],
    )

    req.mark_complete(seq_id, "B1", "P1", "S1", "step1")
    req.mark_complete(seq_id, "B1", "P1", "S1", "step2")

    print(req.is_sample_completed(seq_id, "B1", "P1", "S1"))  # False

    req.mark_complete(seq_id, "B1", "P1", "S1", "step3")

    print(req.is_sample_completed(seq_id, "B1", "P1", "S1"))  # True
    print(req.is_batch_completed(seq_id, "B1"))  # True
    print(req.is_sequence_completed(seq_id))  # True
    print(req.is_all_completed())  # True (Request 전체 완료)
    pass
