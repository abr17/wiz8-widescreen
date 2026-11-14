# Isolated Linux bench: Ubuntu's Wine 9.0 and GE-Proton in one image, with clean prefixes
# baked in. Built and started by linux_bench.ps1 (docs/testing.md, "Linux / Proton bench").
#   docker build -t wiz8-linux-bench:1 scripts/linux
# The image holds no game files: the game, the patch package and the output folder are mounted
# at run time (/game and /patch read-only, /out writable). Entry point: bench.sh. The same image
# is also imported as a throw-away WSL2 distro for linux_bench.ps1 -Show (sandbox.sh, wsl.conf).

# GE-Proton10-25 (github.com/GloriousEggroll/proton-ge-custom, release GE-Proton10-25),
# downloaded at build time. SHA-256 of GE-Proton10-25.tar.gz computed on 2026-10-25; the file
# also matches the release's own GE-Proton10-25.sha512sum. A new version needs a new checksum.
FROM scratch AS proton-download
ADD --chmod=644 --checksum=sha256:b0e4a71cd8a6110a222934d5512725110c0e3b780f5f293d127a6d1eb9c8ba6d \
    https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton10-25/GE-Proton10-25.tar.gz \
    /proton.tar.gz

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8

# Wine 9.0 from Ubuntu (wine64 + wine32), X without a screen (Xvfb) or in a window (Xephyr, for
# -Show), input (xdotool) and screenshots (xwd + ImageMagick), Python for Proton's launcher,
# Mesa software drivers for both architectures: llvmpipe (OpenGL, Wine's wined3d) and
# lavapipe (Vulkan, Proton's DXVK). The X/GL libraries are listed by hand because Wine only
# recommends them. Mesa's 64-bit d3d12 driver (in libgl1-mesa-dri) draws on the Windows GPU
# with -Gpu; glxinfo (mesa-utils) names the OpenGL renderer in summary.txt.
RUN dpkg --add-architecture i386 \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      wine wine64 wine32:i386 fonts-wine \
      xvfb xserver-xephyr xdotool x11-apps imagemagick python3 mesa-utils \
      libgl1 libgl1:i386 libglx-mesa0 libglx-mesa0:i386 libgl1-mesa-dri libgl1-mesa-dri:i386 \
      libvulkan1 libvulkan1:i386 mesa-vulkan-drivers mesa-vulkan-drivers:i386 \
      libxcomposite1 libxcomposite1:i386 libxcursor1 libxcursor1:i386 libxfixes3 libxfixes3:i386 \
      libxi6 libxi6:i386 libxinerama1 libxinerama1:i386 libxrandr2 libxrandr2:i386 \
      libxrender1 libxrender1:i386 libxxf86vm1 libxxf86vm1:i386 \
      libgnutls30t64 libgnutls30t64:i386 libdbus-1-3 libdbus-1-3:i386 \
 && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

# Non-root user (uid 1000 replaces Ubuntu's default "ubuntu" user). Proton writes lock files
# next to its script, so the bench user owns /opt/proton.
RUN userdel -r ubuntu 2>/dev/null; useradd -m -u 1000 -s /bin/bash bench \
 && mkdir -p /opt/bench /opt/proton /game /patch /out \
 && chown bench:bench /opt/proton /out
USER bench
ENV HOME=/home/bench
WORKDIR /home/bench
RUN --mount=type=bind,from=proton-download,source=/proton.tar.gz,target=/tmp/proton.tar.gz \
    tar -xzf /tmp/proton.tar.gz -C /opt/proton --strip-components=1 \
 && test "$(cut -d' ' -f2 /opt/proton/version)" = GE-Proton10-25

# Clean prefixes, made once here; every run copies them to a fresh folder.
COPY bake.sh /opt/bench/bake.sh
RUN --mount=type=tmpfs,target=/tmp/bake sed 's/\r$//' /opt/bench/bake.sh | bash

# (the sed calls drop Windows line ends, in case git checked the scripts out with CRLF)
USER root
COPY bench.sh sandbox.sh /opt/bench/
COPY wsl.conf /etc/wsl.conf
RUN sed -i 's/\r$//' /opt/bench/bench.sh /opt/bench/sandbox.sh /etc/wsl.conf \
 && chmod 755 /opt/bench/bench.sh /opt/bench/sandbox.sh
USER bench
ENTRYPOINT ["/opt/bench/bench.sh"]
