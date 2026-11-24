FROM golang:1.24.2-alpine3.21@sha256:7772cb5322baa875edd74705556d08f0eeca7b9c4b5367754ce3f2f00041ccee AS build
WORKDIR /src
ADD --checksum=sha256:c9598dcce3440977e79f787f2ba0e7e4d92c8d556bd51e7cef3785bafd6635f3 https://codeload.github.com/minio/minio/tar.gz/refs/tags/RELEASE.2025-09-07T16-13-09Z /tmp/minio.tar.gz
RUN tar -xzf /tmp/minio.tar.gz --strip-components=1 -C /src
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOMAXPROCS=4 go build -p 2 -trimpath -ldflags="-s -w -X github.com/minio/minio/cmd.Version=RELEASE.2025-09-07T16-13-09Z -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2025-09-07T16-13-09Z" -o /out/minio .

FROM alpine:3.21@sha256:bc21487101ae47172509130ee1092cc273a831968d64b617776d1f69c81e42ab
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build /out/minio /usr/local/bin/minio
RUN mkdir /data && chown 1000:1000 /data
USER 1000:1000
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
