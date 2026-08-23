#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
data_dir="${DATA_DIR:-${repo_root}/data}"
puid="${PUID:-1000}"
pgid="${PGID:-1000}"
directory_mode="${DIRECTORY_MODE:-775}"

umask "${UMASK:-002}"

directories=(
  torrents
  torrents/movies
  torrents/music
  torrents/books
  torrents/tv
  usenet
  usenet/movies
  usenet/music
  usenet/books
  usenet/tv
  media
  media/Movies
  media/Music
  media/Books
  media/TV
)

for directory in "${directories[@]}"; do
  mkdir -p -- "${data_dir}/${directory}"
  chown -- "${puid}:${pgid}" "${data_dir}/${directory}"
  chmod -- "${directory_mode}" "${data_dir}/${directory}"
done

printf 'Data directories initialized under %s\n' "${data_dir}"
