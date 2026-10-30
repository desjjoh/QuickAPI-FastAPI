"""Read and validate the exact OCI archive, runtime and attached build metadata."""

import base64
import hashlib
import json
import re
import tarfile
import urllib.parse
from pathlib import Path
from typing import Any

from scripts.security_policy import (
    invalid_constant,
    mapping,
    normalize,
    sequence,
    text,
    unique_fields,
)

DIGEST = re.compile(r'sha256:[a-f0-9]{64}')


def decode(body: bytes) -> dict[str, Any]:
    return mapping(
        json.loads(
            body, object_pairs_hook=unique_fields, parse_constant=invalid_constant
        )
    )


def source_uri(uri: str) -> str:
    parsed = urllib.parse.urlsplit(uri.removeprefix('git+'))

    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.removesuffix('.git'), '', '')
    )


class Candidate:
    def __init__(self, path: Path) -> None:
        self.archive = tarfile.open(path)
        self.members: dict[str, tarfile.TarInfo] = {}

        try:
            for member in self.archive.getmembers():
                name = member.name.removeprefix('./')

                if member.isdir() and name.rstrip('/') in {'blobs', 'blobs/sha256'}:
                    continue

                if (
                    not member.isfile()
                    or not re.fullmatch(
                        r'(?:index\.json|oci-layout|blobs/sha256/[a-f0-9]{64})', name
                    )
                    or name in self.members
                ):
                    raise ValueError(
                        'Unsafe, duplicate or unsupported OCI archive entry.'
                    )

                self.members[name] = member
        except Exception:
            self.close()

            raise

    def close(self) -> None:
        self.archive.close()

    def read(self, name: str) -> dict[str, Any]:
        member = self.members[name]

        if member.size > 16 * 1024 * 1024:
            raise ValueError('Oversized OCI metadata.')

        stream = self.archive.extractfile(member)

        if stream is None:
            raise ValueError('Missing OCI metadata.')

        with stream:
            return decode(stream.read())

    def blob(self, descriptor: Any, *, metadata: bool = True) -> dict[str, Any]:
        descriptor = mapping(descriptor)
        digest = text(descriptor.get('digest'))

        if not DIGEST.fullmatch(digest):
            raise ValueError('Invalid OCI descriptor digest.')

        name = 'blobs/sha256/' + digest[7:]
        member = self.members.get(name)

        if member is None:
            encoded = descriptor.get('data')

            if not isinstance(encoded, str) or not 0 < len(encoded) <= 24 * 1024 * 1024:
                raise ValueError('Oversized inline OCI metadata.')

            body = base64.b64decode(encoded, validate=True)

            if (
                len(body) != descriptor.get('size')
                or 'sha256:' + hashlib.sha256(body).hexdigest() != digest
            ):
                raise ValueError('Inline OCI descriptor size/digest differs.')

            return decode(body) if metadata else {}

        if member.size != descriptor.get('size'):
            raise ValueError('OCI descriptor size differs.')

        stream = self.archive.extractfile(member)

        if stream is None:
            raise ValueError('Missing OCI blob.')

        hasher = hashlib.sha256()

        with stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)

        if 'sha256:' + hasher.hexdigest() != digest:
            raise ValueError('OCI blob digest differs.')

        return self.read(name) if metadata else {}

    def extract(self, directory: Path) -> None:
        # Copy regular allowlisted files only; never use archive-controlled paths/links.
        for name, member in self.members.items():
            destination = directory / name

            destination.parent.mkdir(parents=True, exist_ok=True)
            stream = self.archive.extractfile(member)

            if stream is None:
                raise ValueError('Missing OCI archive file.')

            with stream, destination.open('wb') as output:
                while chunk := stream.read(1024 * 1024):
                    output.write(chunk)


def inspect(
    path: Path, source: dict[str, Any], version: str, packages: dict[str, str]
) -> dict[str, Any]:
    candidate = Candidate(path)

    try:
        if candidate.read('oci-layout').get('imageLayoutVersion') != '1.0.0':
            raise ValueError('Unsupported OCI layout.')

        root = candidate.read('index.json')
        roots = sequence(root.get('manifests'))

        if root.get('schemaVersion') != 2 or len(roots) != 1:
            raise ValueError('Expected exactly one OCI candidate index.')

        descriptor = mapping(roots[0])
        index = candidate.blob(descriptor)
        entries = [mapping(entry) for entry in sequence(index.get('manifests'))]
        runtimes = [
            entry
            for entry in entries
            if entry.get('platform') == {'architecture': 'amd64', 'os': 'linux'}
        ]

        if len(runtimes) != 1:
            raise ValueError('Expected one linux/amd64 runtime.')

        runtime = runtimes[0]
        manifest = candidate.blob(runtime)
        config = candidate.blob(manifest.get('config'))
        labels = mapping(mapping(config.get('config')).get('Labels'))

        if (
            config.get('os') != 'linux'
            or config.get('architecture') != 'amd64'
            or labels.get('org.opencontainers.image.revision') != source['sha']
            or labels.get('org.opencontainers.image.source') != source['repository']
            or labels.get('org.opencontainers.image.version') != version
        ):
            raise ValueError(
                'Runtime platform/source/version differs from the selected candidate.'
            )

        for layer in sequence(manifest.get('layers')):
            candidate.blob(layer, metadata=False)

        attestations: dict[str, Any] = {}

        for entry in entries:
            if entry == runtime:
                continue

            attestation = candidate.blob(entry)
            annotations = mapping(entry.get('annotations', {}))
            bindings = [
                value
                for value in (
                    annotations.get('vnd.docker.reference.digest'),
                    mapping(attestation.get('subject', {})).get('digest'),
                )
                if value is not None
            ]

            if (
                not bindings
                or any(value != runtime['digest'] for value in bindings)
                or (
                    annotations.get('vnd.docker.reference.type')
                    != 'attestation-manifest'
                    and attestation.get('artifactType')
                    != 'application/vnd.docker.attestation.manifest.v1+json'
                )
            ):
                raise ValueError('Unrecognized or wrongly bound attestation manifest.')

            # Validate the attestation config blob too, including OCI empty configs.
            candidate.blob(attestation.get('config'))

            for layer in sequence(attestation.get('layers')):
                layer = mapping(layer)
                statement = candidate.blob(layer)
                predicate_type = statement.get('predicateType')

                if (
                    layer.get('mediaType') != 'application/vnd.in-toto+json'
                    or statement.get('_type')
                    not in {
                        'https://in-toto.io/Statement/v0.1',
                        'https://in-toto.io/Statement/v1',
                    }
                    or mapping(layer.get('annotations')).get(
                        'in-toto.io/predicate-type'
                    )
                    != predicate_type
                ):
                    raise ValueError('Unsupported attestation statement.')

                subjects = sequence(statement.get('subject'))

                if any(
                    mapping(mapping(subject).get('digest')).get('sha256')
                    != runtime['digest'][7:]
                    for subject in subjects
                ):
                    raise ValueError('Attestation subject differs from runtime.')

                key = (
                    'sbom'
                    if predicate_type == 'https://spdx.dev/Document'
                    else (
                        'provenance'
                        if predicate_type
                        in {
                            'https://slsa.dev/provenance/v0.2',
                            'https://slsa.dev/provenance/v1',
                        }
                        else None
                    )
                )

                if key is None or key in attestations:
                    raise ValueError('Unsupported or duplicate attestation predicate.')

                attestations[key] = mapping(statement.get('predicate'))

        if set(attestations) != {'sbom', 'provenance'}:
            raise ValueError('Candidate requires SPDX SBOM and provenance.')

        sbom = attestations['sbom']
        inventory = {
            (
                normalize(text(mapping(package).get('name'))),
                text(mapping(package).get('versionInfo')),
            )
            for package in sequence(sbom.get('packages'))
            if mapping(package).get('versionInfo')
        }

        if (
            not text(sbom.get('spdxVersion')).startswith('SPDX-2.')
            or not set(packages.items()) <= inventory
        ):
            raise ValueError('Missing runtime package inventory in SPDX SBOM.')

        provenance = attestations['provenance']
        materials = provenance.get(
            'materials',
            mapping(provenance.get('buildDefinition', {})).get(
                'resolvedDependencies', []
            ),
        )
        vcs = mapping(
            mapping(provenance.get('metadata', {})).get(
                'https://mobyproject.org/buildkit@v1#metadata', {}
            )
        ).get('vcs', {})
        vcs = mapping(
            mapping(mapping(provenance.get('runDetails', {})).get('metadata', {})).get(
                'buildkit_metadata', {}
            )
        ).get('vcs', vcs)
        bound_material = any(
            source_uri(text(mapping(material).get('uri'))) == source['repository']
            and source['sha'] in mapping(mapping(material).get('digest')).values()
            for material in sequence(materials)
        )
        bound_vcs = (
            mapping(vcs).get('revision') == source['sha']
            and source_uri(str(mapping(vcs).get('source', ''))) == source['repository']
        )

        if not bound_material and not bound_vcs:
            raise ValueError('Provenance does not identify the selected source.')

        return {
            'digest': descriptor['digest'],
            'runtimeDigest': runtime['digest'],
            'imageId': mapping(manifest['config'])['digest'],
            **attestations,
        }
    finally:
        candidate.close()
