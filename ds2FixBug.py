import discord
from discord.ext import commands
import asyncio
import os
import uuid
import re

def is_valid_url(url):
    """Controlla se l'URL è valido per yt-dlp"""
    # Regex semplice per controllare link YouTube o SoundCloud
    youtube_regex = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
    soundcloud_regex = r"(https?://)?(www\.)?(soundcloud\.com)/.+"
    return re.match(youtube_regex, url) or re.match(soundcloud_regex, url)


# Setup bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Percorso di ffmpeg
FFMPEG_PATH = r"C:\Users\BT1gg\Desktop\ffmpeg-2025-04-23-git-25b0a8e295-full_build\bin\ffmpeg.exe"

class GuildAudioData:
    def __init__(self):
        self.queue = []
        self.current_song = None
        self.repeat = False
        self.vc = None
        self.current_filename = None
        self.message_channel = None

guild_data = {}

@bot.event
async def on_ready():
    print(f"✅ Bot connesso come {bot.user}")
    await bot.change_presence(activity=discord.Game(name="SoundsBot 🎵"), status=discord.Status.idle)
    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash commands sincronizzati ({len(synced)} comandi)")
    except Exception as e:
        print(f"❌ Errore sync: {e}")

async def download_audio(url, guild_id):
    """Scarica l'audio e lo salva in un file mp3 valido."""
    unique_id = str(uuid.uuid4())[:8]
    filename = f"temp_song_{guild_id}_{unique_id}.mp3"

    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", filename,
        "--ffmpeg-location", "C:\\Users\\BT1gg\\Desktop\\ffmpeg-2025-04-23-git-25b0a8e295-full_build\\bin",
        url
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(f"Errore nel download: {stderr.decode()}")
        return None

    if not os.path.exists(filename):
        print(f"❌ File non trovato: {filename}")
        return None

    if guild_id in guild_data:
        guild_data[guild_id].current_filename = filename
    return filename

async def cleanup_file(guild_id):
    if guild_id not in guild_data:
        return

    file = guild_data[guild_id].current_filename
    if not file or not os.path.exists(file):
        return

    max_attempts = 5
    attempt = 0

    while attempt < max_attempts:
        try:
            os.remove(file)
            print(f"🗑️ File eliminato correttamente: {file}")
            break
        except PermissionError as e:
            attempt += 1
            print(f"⚠️ Tentativo {attempt}: file ancora in uso... ritento tra 1 secondo.")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ Errore eliminazione file: {str(e)}")
            break

    # Se ancora fallisce dopo i tentativi
    if attempt == max_attempts:
        print(f"❌ Non sono riuscito a eliminare il file dopo {max_attempts} tentativi: {file}")

    guild_data[guild_id].current_filename = None

async def play_next(interaction, vc, guild_id):
    guild_audio = guild_data.get(guild_id)
    if not guild_audio:
        return

    await cleanup_file(guild_id)

    if guild_audio.repeat and guild_audio.current_song:
        filename = await download_audio(guild_audio.current_song, guild_id)
        if filename:
            source = discord.FFmpegPCMAudio(filename, executable=FFMPEG_PATH)
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction, vc, guild_id), bot.loop))
            if guild_audio.message_channel:
                await guild_audio.message_channel.send(f"🔁 Ripetendo: {guild_audio.current_song}")
        return

    if guild_audio.queue:
        next_url = guild_audio.queue.pop(0)
        filename = await download_audio(next_url, guild_id)
        if filename:
            guild_audio.current_song = next_url
            source = discord.FFmpegPCMAudio(filename, executable=FFMPEG_PATH)
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction, vc, guild_id), bot.loop))
            if guild_audio.message_channel:
                await guild_audio.message_channel.send(f"🎶 Ora suona: {next_url}")
    else:
        guild_audio.current_song = None
        if vc.is_connected():
            await vc.disconnect()
            if guild_audio.message_channel:
                await guild_audio.message_channel.send("⏹️ Coda finita, disconnesso.")


@bot.tree.command(name="play", description="Riproduce o aggiunge una canzone da URL")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    guild_id = interaction.guild.id

    # 🔥 Prima controllo l'URL 🔥
    if not is_valid_url(url):
        await interaction.followup.send("❌ URL non valido! Inserisci un link corretto di YouTube o SoundCloud.")
        return

    if guild_id not in guild_data:
        guild_data[guild_id] = GuildAudioData()

    guild_audio = guild_data[guild_id]
    guild_audio.message_channel = interaction.channel

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("🔊 Devi essere in un canale vocale!")
        return

    try:
        if not interaction.guild.voice_client:
            vc = await interaction.user.voice.channel.connect()
            guild_audio.vc = vc
        else:
            vc = interaction.guild.voice_client
            guild_audio.vc = vc
    except Exception as e:
        await interaction.followup.send(f"❌ Errore connessione: {e}")
        return

    if vc.is_playing() or guild_audio.queue:
        guild_audio.queue.append(url)
        await interaction.followup.send(f"➕ Aggiunto alla coda: {len(guild_audio.queue)} canzoni.")
    else:
        filename = await download_audio(url, guild_id)
        if filename:
            guild_audio.current_song = url
            source = discord.FFmpegPCMAudio(filename, executable=FFMPEG_PATH)
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction, vc, guild_id), bot.loop))
            await interaction.followup.send(f"🎶 Riproducendo: {url}")

# Gli altri comandi
@bot.tree.command(name="pause", description="Metti in pausa")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Pausa.")
    else:
        await interaction.response.send_message("❌ Nessuna musica da mettere in pausa.")

@bot.tree.command(name="resume", description="Riprendi")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Ripreso.")
    else:
        await interaction.response.send_message("❌ Nessuna musica da riprendere.")

@bot.tree.command(name="stop", description="Ferma")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
    await cleanup_file(guild_id)
    guild_data[guild_id] = GuildAudioData()
    await interaction.response.send_message("⏹️ Fermato e disconnesso.")

@bot.tree.command(name="repeat", description="Ripeti la canzone attuale all'infinito")
async def repeat(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guild_data:
        await interaction.response.send_message("❌ Nessuna canzone in riproduzione.")
        return

    guild_audio = guild_data[guild_id]
    guild_audio.repeat = not guild_audio.repeat
    stato = "attivato 🔁" if guild_audio.repeat else "disattivato ❌"
    await interaction.response.send_message(f"Modalità ripetizione {stato}.")

@bot.tree.command(name="skip", description="Salta la canzone attuale")
async def skip(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guild_data:
        await interaction.response.send_message("❌ Nessuna canzone in riproduzione.")
        return

    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭️ Canzone saltata!")
    else:
        await interaction.response.send_message("❌ Nessuna canzone in riproduzione.")

@bot.tree.command(name="queue", description="Mostra la coda")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue = guild_data[guild_id].queue if guild_id in guild_data else []
    if not queue:
        await interaction.response.send_message("📭 La coda è vuota.")
    else:
        msg = "\n".join([f"{i+1}. {song}" for i, song in enumerate(queue)])
        await interaction.response.send_message(f"🎶 Coda:\n{msg}")

@bot.tree.command(name="clearqueue", description="Svuota la coda")
async def clearqueue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in guild_data:
        guild_data[guild_id].queue.clear()
    await interaction.response.send_message("🗑️ Coda svuotata!")

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user and not after.channel:
        guild_id = member.guild.id
        await cleanup_file(guild_id)
        if guild_id in guild_data:
            guild_data[guild_id] = GuildAudioData()


bot.run('MTM2NjA3MDkxNTkxMzIyNDMwNQ.GfMRBv.6K24wG4wshkgdAvpYJPNYotf--aR-ZUfnFZPco')