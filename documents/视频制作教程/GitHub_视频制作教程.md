# GitHub 视频制作相关开源资源

> 采集时间：2026-06-26 00:44
> 采集数量：9 个项目

---

## 按 Star 数排序

### 1. [openai/whisper](https://github.com/openai/whisper)

**描述**: Robust Speech Recognition via Large-Scale Weak Supervision

| 属性 | 值 |
|------|-----|
| Star | 103617 |
| Fork | 12617 |
| 语言 | Python |
| 许可证 | MIT License |
| 标签 |  |

**README 摘要**:

# Whisper

[[Blog]](https://openai.com/blog/whisper)
[[Paper]](https://arxiv.org/abs/2212.04356)
[[Model card]](https://github.com/openai/whisper/blob/main/model-card.md)
[[Colab example]](https://colab.research.google.com/github/openai/whisper/blob/master/notebooks/LibriSpeech.ipynb)

Whisper is a general-purpose speech recognition model. It is trained on a large dataset of diverse audio and is also a multitasking model that can perform multilingual speech recognition, speech translation, and language identification.

## Approach

A Transformer sequence-to-sequence model is trained on various speech processing tasks, including multilingual speech recognition, speech translation, spoken language identification, and voice activity detection. These tasks are jointly represented as a sequence of tokens to be predicted by the decoder, allowing a single model to replace many stages of a traditional speech-processing pipeline. The multitask training format uses a set of special tokens that serve as task specifiers or classification targets.

## Setup

We used Python 3.9.9 and [PyTorch](https://pytorch.org/) 1.10.1 to train and test our models, but the codebase is expected to be compatible with Python 3.8-3.11 and recent PyTorch versions. The codebase also depends on a few Python packages, most notably [OpenAI's tiktoken](https://github.com/openai/tiktoken) for their fast tokenizer implementation. You can download and install (or update to) the latest release of Whisper with the following command:

    pip install -U openai-whisper

Alternatively, the following command will pull and install the latest commit from this repository, along with its Python dependencies:

    pip install git+https://github.com/openai/whisper.git 

To update the package to the latest version of this repository, please run:

    pip install --upgrade --no-deps --force-reinstall git+https://github.com/openai/whisper.git

It also requires the command-line tool [`ffmpeg`](https://ffmpeg.org/) to be installed on your system, which is available from most package managers:

```bash
# on Ubuntu or Debian
sudo apt update && sudo apt install ffmpeg

# on Arch Linux
sudo pacman -S ffmpeg

# on MacOS using Homebrew (https://brew.sh/)
brew install ffmpeg

# on Windows using Chocolatey (https://chocolatey.org/)
choco install ffmpeg

# on Windows using Scoop (https://scoop.sh/)
scoop install ffmpeg
```

You may need [`rust`](http://rust-lang.org) installed as well, in case [tiktoken](https://github.com/openai/tiktoken) does not provide a pre-built wheel for your platform. If you see installation errors during the `pip install` command above, please follow the [Getting started page](https://www.rust-lang.org/learn/get-started) to install Rust development environment. Additionally, you may need to configure the `PATH` environment variable, e.g. `export PATH="$HOME/.cargo/bin:$PATH"`. If the installation fails with `No module named 'setuptools_rust'`, you need to install `setuptools_rust`, e.g. by running:

```bash
pip install setuptools-rust
```

## Available models and languages

There are six model sizes, four with English-only versions, offering speed and accuracy tradeoffs.
Below are the names of the available models and their approximate memory requirements and inference speed relative to the large model.
The relative speeds below are measured by transcribing English speech on a A100, and the real-world speed may vary significantly depending on many factors including the language, the speaking speed, and the available hardware.

|  Size  | Parameters | English-only model | Multilingual model | Required VRAM | Relative speed |
|:------:|:----------:|:------------------:|:------------------:|:-------------:|:--------------:|
|  tiny  |    39 M    |     `tiny.en`      |       `tiny`       |     ~1 GB     |      ~10x      |
|  base  |    74 M    |     `base.en`      |       `base`       |     ~1 GB     |      ~7x       |
| small  |   244 M    |     `small.en`     |      `small`       |     ~2 GB     |      ~4x       |
| medium |   769 M    |    `medium.en`     |      `medium`      |     ~5 GB     |      ~2x       |
| large  |   1550 M   |        N/A         |      `large`       |    ~10 GB     |       1x       |
| turbo  |   809 M    |        N/A         |      `turbo`       |     ~6 GB     |      ~8x       |

The `.en` models for English-only applications tend to perform better, especially for the `tiny.en` and `base.en` models. We observed that the difference becomes less significant for the `small.en` and `medium.en` models.
Additionally, the `turbo` model is an optimized version of `large-v3` that offers faster transcription speed with a minimal degradation in accuracy.

Whisper's performance varies widely depending on the language. The figure below shows a performance breakdown of `large-v3` and `large-v2` models by language, using WERs (word error rates) or CER (character error rates, shown in *Italic*) evaluated on the Common Voice 15 and Fleurs 

...(内容已截断)

---

### 2. [opencv/opencv](https://github.com/opencv/opencv)

**描述**: Open Source Computer Vision Library

| 属性 | 值 |
|------|-----|
| Star | 89380 |
| Fork | 56657 |
| 语言 | C++ |
| 许可证 | Apache License 2.0 |
| 标签 | c-plus-plus, computer-vision, deep-learning, image-processing, opencv |

**README 摘要**:

## OpenCV: Open Source Computer Vision Library

### Resources

* Homepage: <https://opencv.org>
  * Courses: <https://opencv.org/courses>
* Docs: <https://docs.opencv.org/4.x/>
* Q&A forum: <https://forum.opencv.org>
  * previous forum (read only): <http://answers.opencv.org>
* Issue tracking: <https://github.com/opencv/opencv/issues>
* Additional OpenCV functionality: <https://github.com/opencv/opencv_contrib>
* Donate to OpenCV: <https://opencv.org/support/>

### Contributing

Please read the [contribution guidelines](https://github.com/opencv/opencv/wiki/How_to_contribute) before starting work on a pull request.

#### Summary of the guidelines:

* One pull request per issue;
* Choose the right base branch;
* Include tests and documentation;
* Clean up "oops" commits before submitting;
* Follow the [coding style guide](https://github.com/opencv/opencv/wiki/Coding_Style_Guide).

### Additional Resources

* [Submit your OpenCV-based project](https://form.jotform.com/233105358823151) for inclusion in Community Friday on opencv.org
* [Subscribe to the OpenCV YouTube Channel](http://youtube.com/@opencvofficial) featuring OpenCV Live, an hour-long streaming show
* [Follow OpenCV on LinkedIn](http://linkedin.com/company/opencv/) for daily posts showing the state-of-the-art in computer vision & AI
* [Apply to be an OpenCV Volunteer](https://form.jotform.com/232745316792159) to help organize events and online campaigns as well as amplify them
* [Follow OpenCV on Mastodon](http://mastodon.social/@opencv) in the Fediverse
* [Follow OpenCV on Twitter](https://twitter.com/opencvlive)
* [OpenCV.ai](https://opencv.ai): Computer Vision and AI development services from the OpenCV team.

---

### 3. [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg)

**描述**: Mirror of https://git.ffmpeg.org/ffmpeg.git

| 属性 | 值 |
|------|-----|
| Star | 61441 |
| Fork | 13932 |
| 语言 | C |
| 许可证 | Other |
| 标签 | audio, c, ffmpeg, fft, hevc, hls, matroska, mp4, mpeg, multimedia, rtmp, rtsp, streaming, video, webm |

**README 摘要**:

# FFmpeg README

FFmpeg is a collection of libraries and tools to process multimedia content
such as audio, video, subtitles and related metadata.

## Libraries

* `libavcodec` provides implementation of a wider range of codecs.
* `libavformat` implements streaming protocols, container formats and basic I/O access.
* `libavutil` includes hashers, decompressors and miscellaneous utility functions.
* `libavfilter` provides means to alter decoded audio and video through a directed graph of connected filters.
* `libavdevice` provides an abstraction to access capture and playback devices.
* `libswresample` implements audio mixing and resampling routines.
* `libswscale` implements color conversion and scaling routines.

## Tools

* [ffmpeg](https://ffmpeg.org/ffmpeg.html) is a command line toolbox to
  manipulate, convert and stream multimedia content.
* [ffplay](https://ffmpeg.org/ffplay.html) is a minimalistic multimedia player.
* [ffprobe](https://ffmpeg.org/ffprobe.html) is a simple analysis tool to inspect
  multimedia content.
* Additional small tools such as `aviocat`, `ismindex` and `qt-faststart`.

## Documentation

The offline documentation is available in the **doc/** directory.

The online documentation is available in the main [website](https://ffmpeg.org)
and in the [wiki](https://trac.ffmpeg.org).

### Examples

Coding examples are available in the **doc/examples** directory.

## License

FFmpeg codebase is mainly LGPL-licensed with optional components licensed under
GPL. Please refer to the LICENSE file for detailed information.

## Contributing

Patches should be submitted to the ffmpeg-devel mailing list using
`git format-patch` or `git send-email`. Github pull requests should be
avoided because they are not part of our review process and will be ignored.

---

### 4. [hpcaitech/Open-Sora](https://github.com/hpcaitech/Open-Sora)

**描述**: Open-Sora: Democratizing Efficient Video Production for All

| 属性 | 值 |
|------|-----|
| Star | 29134 |
| Fork | 2977 |
| 语言 | Python |
| 许可证 | Apache License 2.0 |
| 标签 |  |

**README 摘要**:

<p align="center">
    <img src="https://github.com/hpcaitech/Open-Sora-Demo/blob/main/readme/icon.png" width="250"/>
</p>
<div align="center">
    <a href="https://github.com/hpcaitech/Open-Sora/stargazers"><img src="https://img.shields.io/github/stars/hpcaitech/Open-Sora?style=social"></a>
    <a href="https://arxiv.org/abs/2503.09642v1"><img src="https://img.shields.io/static/v1?label=Tech Report 2.0&message=Arxiv&color=red"></a>
    <a href="https://arxiv.org/abs/2412.20404"><img src="https://img.shields.io/static/v1?label=Tech Report 1.2&message=Arxiv&color=red"></a>
    <a href="https://hpcaitech.github.io/Open-Sora/"><img src="https://img.shields.io/badge/Gallery-View-orange?logo=&amp"></a>
</div>

<div align="center">
    <a href="https://discord.gg/kZakZzrSUT"><img src="https://img.shields.io/badge/Discord-join-blueviolet?logo=discord&amp"></a>
    <a href="https://join.slack.com/t/colossalaiworkspace/shared_invite/zt-247ipg9fk-KRRYmUl~u2ll2637WRURVA"><img src="https://img.shields.io/badge/Slack-ColossalAI-blueviolet?logo=slack&amp"></a>
    <a href="https://x.com/YangYou1991/status/1899973689460044010"><img src="https://img.shields.io/badge/Twitter-Discuss-blue?logo=twitter&amp"></a>
    <a href="https://raw.githubusercontent.com/hpcaitech/public_assets/main/colossalai/img/WeChat.png"><img src="https://img.shields.io/badge/微信-小助手加群-green?logo=wechat&amp"></a>
</div>

## Open-Sora: Democratizing Efficient Video Production for All

We design and implement **Open-Sora**, an initiative dedicated to **efficiently** producing high-quality video. We hope to make the model,
tools and all details accessible to all. By embracing **open-source** principles,
Open-Sora not only democratizes access to advanced video generation techniques, but also offers a
streamlined and user-friendly platform that simplifies the complexities of video generation.
With Open-Sora, our goal is to foster innovation, creativity, and inclusivity within the field of content creation.

🎬 For a professional AI video-generation product, try [Video Ocean](https://video-ocean.com/) — powered by a superior model.
<div align="center">
   <a href="https://video-ocean.com/">
   <img src="https://github.com/hpcaitech/public_assets/blob/main/colossalai/img/3.gif" width="850" />
   </a>
</div>

<div align="center">
   <a href="https://hpc-ai.com/?utm_source=github&utm_medium=social&utm_campaign=promotion-opensora">
   <img src="https://github.com/hpcaitech/public_assets/blob/main/colossalai/img/1.gif" width="850" />
   </a>
</div>

<div align="center">
   <a href="https://hpc-ai.com/model-apis?utm_source=github&utm_medium=social&utm_campaign=promotion-opensora">
   <img src="https://github.com/hpcaitech/public_assets/blob/main/colossalai/img/0408.gif" width="850" />
   </a>
</div>

<!-- [[中文文档](/docs/zh_CN/README.md)] [[潞晨云](https://cloud.luchentech.com/)|[OpenSora镜像](https://cloud.luchentech.com/doc/docs/image/open-sora/)|[视频教程](https://www.bilibili.com/video/BV1ow4m1e7PX/?vd_source=c6b752764cd36ff0e535a768e35d98d2)] -->

## 📰 News

- **[2025.03.12]** 🔥 We released **Open-Sora 2.0** (11B). 🎬 11B model achieves [on-par performance](#evaluation) with 11B HunyuanVideo & 30B Step-Video on 📐VBench & 📊Human Preference. 🛠️ Fully open-source: checkpoints and training codes for training with only **$200K**. [[report]](https://arxiv.org/abs/2503.09642v1)
- **[2025.02.20]** 🔥 We released **Open-Sora 1.3** (1B). With the upgraded VAE and Transformer architecture, the quality of our generated videos has been greatly improved 🚀. [[checkpoints]](#open-sora-13-model-weights) [[report]](/docs/report_04.md) [[demo]](https://huggingface.co/spaces/hpcai-tech/open-sora)
- **[2024.12.23]** The development cost of video generation models has saved by 50%! Open-source solutions are now available with H200 GPU vouchers. [[blog]](https://company.hpc-ai.com/blog/the-development-cost-of-video-generation-models-has-saved-by-50-open-source-solutions-are-now-available-with-h200-gpu-vouchers) [[code]](https://github.com/hpcaitech/Open-Sora/blob/main/scripts/train.py) [[vouchers]](https://colossalai.org/zh-Hans/docs/get_started/bonus/)
- **[2024.06.17]** We released **Open-Sora 1.2**, which includes **3D-VAE**, **rectified flow**, and **score condition**. The video quality is greatly improved. [[checkpoints]](#open-sora-12-model-weights) [[report]](/docs/report_03.md) [[arxiv]](https://arxiv.org/abs/2412.20404)
- **[2024.04.25]** 🤗 We released the [Gradio demo for Open-Sora](https://huggingface.co/spaces/hpcai-tech/open-sora) on Hugging Face Spaces.
- **[2024.04.25]** We released **Open-Sora 1.1**, which supports **2s~15s, 144p to 720p, any aspect ratio** text-to-image, **text-to-video, image-to-video, video-to-video, infinite time** generation. In addition, a full video processing pipeline is released. [[checkpoints]](#open-sora-11-model-weights) [[report]](/docs/report_02.md)
- **[2024.03.18]** We released **Open-Sora 1.0**, a fully open-source project for video generation.


...(内容已截断)

---

### 5. [ossrs/srs](https://github.com/ossrs/srs)

**描述**: SRS is a simple, high-efficiency, real-time media server supporting RTMP, WebRTC, HLS, HTTP-FLV, HTTP-TS, SRT, MPEG-DASH, and GB28181, with codec support for H.264, H.265, AV1, VP9, AAC, Opus, and G.711.

| 属性 | 值 |
|------|-----|
| Star | 29006 |
| Fork | 5681 |
| 语言 | C++ |
| 许可证 | MIT License |
| 标签 | audio, c, c-plus-plus, dash, hevc, hls, live, live-streaming, low-latency, media-server, multimedia, prometheus-exporter, rtmp, server-side, srt, streaming, video, video-conferencing, video-streaming, webrtc |

**README 摘要**:

# SRS(Simple Realtime Server)

![](http://ossrs.net/gif/v1/sls.gif?site=github.com&path=/srs/4.0release)
[![](https://github.com/ossrs/srs/actions/workflows/codeql-analysis.yml/badge.svg?branch=4.0release)](https://github.com/ossrs/srs/actions?query=workflow%3ACodeQL+branch%3A4.0release)
[![](https://github.com/ossrs/srs/actions/workflows/release.yml/badge.svg)](https://github.com/ossrs/srs/actions/workflows/release.yml?query=workflow%3ARelease)
[![](https://github.com/ossrs/srs/actions/workflows/test.yml/badge.svg?branch=4.0release)](https://github.com/ossrs/srs/actions?query=workflow%3ATest+branch%3A4.0release)
[![](https://codecov.io/gh/ossrs/srs/branch/4.0release/graph/badge.svg)](https://codecov.io/gh/ossrs/srs/branch/4.0release)
[![](https://ossrs.net/wiki/images/wechat-badge4.svg)](../../wikis/Contact#wechat)
[![](https://ossrs.net/wiki/images/srs-faq.svg)](https://github.com/ossrs/srs/issues/2716)
[![](https://ossrs.net/wiki/images/mulan-incubating.svg)](http://mulanos.cn)
[![](https://ossrs.net/wiki/images/srs-alternativeto.svg)](https://alternativeto.net/software/srs/about/)
[![](https://img.shields.io/youtube/channel/views/UCP6ZblCL_fIJoEyUzZxC1ng?style=social)](https://www.youtube.com/channel/UCP6ZblCL_fIJoEyUzZxC1ng)
[![](https://badgen.net/discord/members/yZ4BnPmHAd)](https://discord.gg/yZ4BnPmHAd)
[![](https://opencollective.com/srs-server/tiers/badge.svg)](https://opencollective.com/srs-server/contribute)
[![](https://badgen.net/badge/srs/stackoverflow/orange?icon=terminal)](https://stackoverflow.com/questions/tagged/simple-realtime-server)
[![](https://img.shields.io/docker/pulls/ossrs/srs)](https://hub.docker.com/r/ossrs/srs/tags)

SRS/4.0，[Leo](https://github.com/ossrs/srs/wiki/Product#release40)，是一个简单高效的实时视频服务器，支持RTMP/WebRTC/HLS/HTTP-FLV/SRT。

SRS is a simple, high efficiency and realtime video server, supports RTMP/WebRTC/HLS/HTTP-FLV/SRT.

[![SRS Overview](https://ossrs.net/wiki/images/SRS-SingleNode-4.0-sd.png?v=114)](https://ossrs.net/wiki/images/SRS-SingleNode-4.0-hd.png)

> Note:  The single node architecture for SRS, for detail please see [here](https://www.figma.com/file/333POxVznQ8Wz1Rxlppn36/SRS-4.0-Server-Arch).

SRS is licenced under [MIT][LICENSE], but some depended libraries are distributed using their [own licenses][LicenseMixing].

<a name="product"></a>
<a name="usage-docker"></a>
## Usage

Build SRS from source:

```
git clone -b 4.0release https://gitee.com/ossrs/srs.git &&
cd srs/trunk && ./configure && make && ./objs/srs -c conf/srs.conf
```

Open [http://localhost:8080/](http://localhost:8080/) to check it, then publish
by [FFmpeg](https://ffmpeg.org/download.html) or [OBS](https://obsproject.com/download) as:

```bash
ffmpeg -re -i ./doc/source.flv -c copy -f flv -y rtmp://localhost/live/livestream
```

Play the following streams by [players](https://ossrs.net):

* RTMP (by [VLC](https://www.videolan.org/)): rtmp://localhost/live/livestream
* H5(HTTP-FLV): [http://localhost:8080/live/livestream.flv](http://localhost:8080/players/srs_player.html?autostart=true&stream=livestream.flv&port=8080&schema=http)
* H5(HLS): [http://localhost:8080/live/livestream.m3u8](http://localhost:8080/players/srs_player.html?autostart=true&stream=livestream.m3u8&port=8080&schema=http)

Note that if convert RTMP to WebRTC, please use [`rtmp2rtc.conf`](https://github.com/ossrs/srs/issues/2728#issuecomment-964686152):

* H5(WebRTC): [webrtc://localhost/live/livestream](http://localhost:8080/players/rtc_player.html?autostart=true)

> Note: Besides of FFmpeg or OBS, it's also able to [publish by H5](http://localhost:8080/players/rtc_publisher.html?autostart=true) 
> if [WebRTC](https://github.com/ossrs/srs/issues/307) is enabled.

> Highly recommend that directly run SRS by
> **docker([CN](https://github.com/ossrs/srs/wiki/v4_CN_Home#docker) / [EN](https://github.com/ossrs/srs/wiki/v4_EN_Home#docker))**,
> **Cloud Virtual Machine([CN](https://github.com/ossrs/srs/wiki/v4_CN_Home#cloud-virtual-machine) / [EN](https://github.com/ossrs/srs/wiki/v4_EN_Home#cloud-virtual-machine))**,
> or **K8s([CN](https://github.com/ossrs/srs/wiki/v4_CN_Home#k8s) / [EN](https://github.com/ossrs/srs/wiki/v4_EN_Home#k8s))**,
> however it's also easy to build SRS from source code, for detail please see
> **Getting Started([CN](https://github.com/ossrs/srs/wiki/v4_CN_Home#getting-started) / [EN](https://github.com/ossrs/srs/wiki/v4_EN_Home#getting-started))**.

> Note: If need HTTPS, by which WebRTC and modern browsers require, please read
> **HTTPS API([CN](https://github.com/ossrs/srs/wiki/v4_CN_HTTPApi#https-api) / [EN](https://github.com/ossrs/srs/wiki/v4_EN_HTTPApi#https-api))**
> and **HTTPS Callback([CN](https://github.com/ossrs/srs/wiki/v4_CN_HTTPCallback#https-callback) / [EN](https://github.com/ossrs/srs/wiki/v4_EN_HTTPCallback#https-callback))**
> and **HTTPS Live Streaming([CN](https://github.com/ossrs/srs/wiki/v4_EN_DeliveryHttpStream#https-flv-live-stream) / [EN](https://github.com/ossrs/srs/wiki/v4_E

...(内容已截断)

---

### 6. [facebookresearch/pytorchvideo](https://github.com/facebookresearch/pytorchvideo)

**描述**: A deep learning library for video understanding research.

| 属性 | 值 |
|------|-----|
| Star | 3565 |
| Fork | 430 |
| 语言 | Python |
| 许可证 | Apache License 2.0 |
| 标签 |  |

**README 摘要**:

<p align="center">
 <img width="130%" src="./.github/media/logo_horizontal_color.png" />
</p>

<p align="center">
   <a href="https://github.com/facebookresearch/pytorchvideo/blob/main/LICENSE">
    <img src="https://img.shields.io/pypi/l/pytorchvideo" alt="CircleCI" />
  </a>
   <a href="https://pypi.org/project/pytorchvideo/">
    <img src="https://img.shields.io/pypi/v/pytorchvideo?color=blue&label=release" alt="CircleCI" />
  </a>
    <a href="https://circleci.com/gh/facebookresearch/pytorchvideo/tree/main">
    <img src="https://img.shields.io/circleci/build/github/facebookresearch/pytorchvideo/main?token=efdf3ff5b6f6acf44f4af39b683dea31d40e5901" alt="Coverage" />
  </a>
    <a href="https://codecov.io/gh/facebookresearch/pytorchvideo/branch/main">
    <img src="https://codecov.io/gh/facebookresearch/pytorchvideo/branch/main/graph/badge.svg?token=OSZSI6JU31"/>
  </a>
  </a>
    <a href="https://pytorchvideo.slack.com/join/shared_invite/zt-wx8xsblj-eAfx6wox9tSuFrAm8KaiPg#/shared-invite/email">
    <img src="http://img.shields.io/static/v1?label=Join%20us%20on&message=%23pytorchvideo&labelColor=%234A154B&logo=slack"/>
  </a>
  <p align="center">
    <i> A deep learning library for video understanding research.</i>
  </p>
  <p align="center">
    <i>Check the <a href="https://pytorchvideo.org/">website</a> for more information.</i>
  </p>
 </p>

|<img src="https://media.giphy.com/media/clMMFBLywc4Sa3KXDb/giphy.gif" width="200"> | <img src=".github/media/ava_slowfast.gif" width="1300">
|:-------------------------------:|:--------------------------------------------------:|
| A PyTorchVideo-accelerated X3D model running on a Samsung Galaxy S10 phone. The model runs ~8x faster than real time, requiring roughly 130 ms to process one second of video.| A PyTorchVideo-based SlowFast model performing video action detection.|

## X3D model Web Demo
Integrated to [Huggingface Spaces](https://huggingface.co/spaces) with [Gradio](https://github.com/gradio-app/gradio). See demo: [![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue)](https://huggingface.co/spaces/pytorch/X3D)

## Introduction

PyTorchVideo is a deeplearning library with a focus on video understanding work. PytorchVideo provides reusable, modular and efficient components needed to accelerate the video understanding research. PyTorchVideo is developed using [PyTorch](https://pytorch.org) and supports different deeplearning video components like video models, video datasets, and video-specific transforms.

Key features include:

- **Based on PyTorch:** Built using PyTorch. Makes it easy to use all of the PyTorch-ecosystem components.
- **Reproducible Model Zoo:** Variety of state of the art pretrained video models and their associated benchmarks that are ready to use.
  Complementing the model zoo, PyTorchVideo comes with extensive data loaders supporting different datasets.
- **Efficient Video Components:** Video-focused fast and efficient components that are easy to use. Supports accelerated inference on hardware.

## Updates

- Aug 2021: [Multiscale Vision Transformers](https://arxiv.org/abs/2104.11227) has been released in PyTorchVideo, details can be found from [here](https://github.com/facebookresearch/pytorchvideo/blob/main/pytorchvideo/models/vision_transformers.py#L97).

## Installation

Install PyTorchVideo inside a conda environment(Python >=3.7) with
```shell
pip install pytorchvideo
```

For detailed instructions please refer to [INSTALL.md](INSTALL.md).

## License

PyTorchVideo is released under the [Apache 2.0 License](LICENSE).

## Tutorials

Get started with PyTorchVideo by trying out one of our [tutorials](https://pytorchvideo.org/docs/tutorial_overview) or by running examples in the [tutorials folder](./tutorials).

## Model Zoo and Baselines
We provide a large set of baseline results and trained models available for download in the [PyTorchVideo Model Zoo](https://github.com/facebookresearch/pytorchvideo/blob/main/docs/source/model_zoo.md).

## Contributors

Here is the growing list of PyTorchVideo contributors in alphabetical order (let us know if you would like to be added):
[Aaron Adcock](https://www.linkedin.com/in/aaron-adcock-79855383/), [Amy Bearman](https://www.linkedin.com/in/amy-bearman/), [Bernard Nguyen](https://www.linkedin.com/in/mrbernardnguyen/), [Bo Xiong](https://www.cs.utexas.edu/~bxiong/), [Chengyuan Yan](https://www.linkedin.com/in/chengyuan-yan-4a804282/), [Christoph Feichtenhofer](https://feichtenhofer.github.io/), [Dave Schnizlein](https://www.linkedin.com/in/david-schnizlein-96020136/), [Haoqi Fan](https://haoqifan.github.io/), [Heng Wang](https://hengcv.github.io/), [Jackson Hamburger](https://www.linkedin.com/in/jackson-hamburger-986a2873/), [Jitendra Malik](http://people.eecs.berkeley.edu/~malik/), [Kalyan Vasudev Alwala](https://www.linkedin.com/in/kalyan-vasudev-alwala-2a802b64/), [Matt Feiszli](https://www.linkedin.com/in/matt-feiszli-76b34b/), [Nikhila Ravi](htt

...(内容已截断)

---

### 7. [PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV)

**描述**: ﻿﻿Pythonic bindings for FFmpeg's libraries.

| 属性 | 值 |
|------|-----|
| Star | 3232 |
| Fork | 439 |
| 语言 | Python |
| 许可证 | BSD 3-Clause "New" or "Revised" License |
| 标签 | ffmpeg, pyav, python |

**README 摘要**:

PyAV
====

PyAV is a Pythonic binding for the [FFmpeg][ffmpeg] libraries. We aim to provide all of the power and control of the underlying library, but manage the gritty details as much as possible.

---

[![GitHub Test Status][github-tests-badge]][github-tests] [![Documentation][docs-badge]][docs] [![Python Package Index][pypi-badge]][pypi] [![Conda Forge][conda-badge]][conda]

PyAV is for direct and precise access to your media via containers, streams, packets, codecs, and frames. It exposes a few transformations of that data, and helps you get your data to/from other packages (e.g. Numpy and Pillow).

This power does come with some responsibility as working with media is horrendously complicated and PyAV can't abstract it away or make all the best decisions for you. If the `ffmpeg` command does the job without you bending over backwards, PyAV is likely going to be more of a hindrance than a help.

But where you can't work without it, PyAV is a critical tool.

Installation
------------

Binary wheels are provided on [PyPI][pypi] for Linux, MacOS and Windows linked against the latest stable version of ffmpeg. You can install these wheels by running:

```bash
pip install av
```

Another way of installing PyAV is via [conda-forge][conda-forge]:

```bash
conda install av -c conda-forge
```

See the [Conda install][conda-install] docs to get started with (mini)Conda.

Alternative installation methods
--------------------------------

Due to the complexity of the dependencies, PyAV is not always the easiest Python package to install from source. If you want to use your existing ffmpeg (must be the correct major version), the source version of PyAV is on [PyPI][pypi]:

> [!WARNING]
> You must be in a posix env, and have the correct version of ffmpeg installed on your system.

```bash
pip install av --no-binary av
```

Installing From Source
----------------------

Here's how to build PyAV from source. You must use [MSYS2](https://www.msys2.org/) when using Windows.

```bash
git clone https://github.com/PyAV-Org/PyAV.git
cd PyAV
source scripts/activate.sh

# Build ffmpeg from source. You can skip this step
# if ffmpeg is already installed.
./scripts/build-deps

# Build PyAV
make

# Testing
make test

# Install globally
deactivate
pip install .
```

---

Have fun, [read the docs][docs], [come chat with us][discuss], and good luck!

[conda-badge]: https://img.shields.io/conda/vn/conda-forge/av.svg?colorB=CCB39A
[conda]: https://anaconda.org/conda-forge/av
[docs-badge]: https://img.shields.io/badge/docs-on%20pyav.basswood.io-blue.svg
[docs]: https://pyav.basswood.io
[pypi-badge]: https://img.shields.io/pypi/v/av.svg?colorB=CCB39A
[pypi]: https://pypi.org/project/av
[discuss]: https://github.com/PyAV-Org/PyAV/discussions

[github-tests-badge]: https://github.com/PyAV-Org/PyAV/workflows/tests/badge.svg
[github-tests]: https://github.com/PyAV-Org/PyAV/actions?workflow=tests
[github]: https://github.com/PyAV-Org/PyAV

[ffmpeg]: https://ffmpeg.org/
[conda-forge]: https://conda-forge.github.io/
[conda-install]: https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html

---

### 8. [runwayml/stable-video-diffusion](https://github.com/runwayml/stable-video-diffusion)

**描述**: 

| 属性 | 值 |
|------|-----|
| Star | 0 |
| Fork | 0 |
| 语言 | Unknown |
| 许可证 | Unknown |
| 标签 |  |

---

### 9. [TencentARC/AnimateDiff](https://github.com/TencentARC/AnimateDiff)

**描述**: 

| 属性 | 值 |
|------|-----|
| Star | 0 |
| Fork | 0 |
| 语言 | Unknown |
| 许可证 | Unknown |
| 标签 |  |

---
