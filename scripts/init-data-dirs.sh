#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
data_dir="${DATA_DIR:-${repo_root}/data}"

directories=(
  torrents/movies
  torrents/music
  torrents/books
  torrents/tv
  usenet/movies
  usenet/music
  usenet/books
  usenet/tv
  media/Movies
  media/Music
  media/Books
  media/TV
)

for directory in "${directories[@]}"; do
  mkdir -p -- "${data_dir}/${directory}"
done

printf 'Data directories initialized under %s\n' "${data_dir}"

