from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Provider, ProviderProbe


def probe_for(session: Session, provider: Provider) -> ProviderProbe:
    query = select(ProviderProbe).where(
        ProviderProbe.provider_id == provider.id, ProviderProbe.org_id == provider.org_id
    )
    probe = session.scalar(query.execution_options(populate_existing=True))
    if not probe:
        try:
            with session.begin_nested():
                probe = ProviderProbe(org_id=provider.org_id, provider_id=provider.id)
                session.add(probe)
                session.flush()
        except IntegrityError:
            probe = session.scalar(query.execution_options(populate_existing=True))
            if not probe:
                raise
    return probe
