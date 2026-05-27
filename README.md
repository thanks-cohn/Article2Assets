# reiser4-linux7

## Reiser4 Linux 7.x Resurrection

### Vision

Reiser4 was one of the most ambitious filesystem projects ever attempted on Linux.

It pursued ideas that still feel futuristic today:

- semantic file organization
- plugin-based filesystem architecture
- efficient handling of small files
- dynamic trees
- flexible metadata models
- filesystem-level extensibility

But time moved on.

Kernel APIs evolved.
Memory management changed.
Folios replaced pages.
VFS internals shifted.
Writeback infrastructure mutated.
The original codebase slowly fossilized against modern Linux.

This repository exists to reverse that process.

---

## What This Project Is

`reiser4-linux7` is an active compatibility and resurrection branch focused on:

- Linux 7.x compatibility
- modern kernel API adaptation
- folio migration
- modern bio/writeback integration
- VFS compatibility restoration
- continued buildability on modern GCC/Clang systems
- preservation of Reiser4's architecture and ideas

The goal is simple:

```bash
git clone https://github.com/thanks-cohn/reiser4-linux7
cd reiser4-linux7
make
sudo make install
sudo modprobe reiser4
```

And Reiser4 lives again on modern Linux systems.

---

## Why This Matters

Modern Linux filesystems are powerful, but many ideas pioneered by Reiser4 remain uniquely compelling.

Reiser4 was not merely a storage format.
It was an exploration of what a filesystem could become.

This project preserves:

- filesystem experimentation
- Linux history
- plugin-oriented filesystem design
- semantic storage concepts
- alternative VFS philosophies

while making them usable again on contemporary systems.

---

## Current Status

This is an active porting effort.

Current work includes:

- folio migration wrappers
- page cache modernization
- bio API compatibility
- writeback subsystem adaptation
- mount API migration
- superblock operation updates
- Linux 7.x kernel compatibility fixes

The filesystem is NOT yet production ready on Linux 7.x.

But the codebase is actively compiling deeper into modern kernels with each compatibility layer restored.

---

## Relationship To Userspace Tools

This repository focuses on the kernel driver.

Userspace tools are maintained separately through:

- mkfs.reiser4
- fsck.reiser4
- debugfs.reiser4
- measurefs.reiser4

via the companion compatibility project:
`fixed-reiser4progs`

---

## Long-Term Goals

- Fully buildable Reiser4 kernel module on Linux 7.x
- DKMS packaging
- Arch/Garuda packaging
- Modern distro compatibility
- Filesystem mounting through standard Linux VFS
- Seamless integration with KDE Dolphin and standard Linux file managers
- Preservation of Reiser4 research and design philosophy

---

## Philosophy

This project is not about nostalgia.

It is about refusing to let powerful ideas disappear merely because APIs changed.

Software archaeology matters.
Filesystem experimentation matters.
Alternative systems thinking matters.

Reiser4 deserves to compile again.
