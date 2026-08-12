"""
Bot Discord qui poste un message de bienvenue automatique quand un nouveau
membre rejoint le serveur, et reagit automatiquement aux messages de trades
gagnants dans #Partage-de-Trades.

Necessite :
- DISCORD_BOT_TOKEN dans .env (cree via https://discord.com/developers/applications)
- Les intents privilegies "Server Members Intent" ET "Message Content Intent"
  actives sur le bot (onglet Bot, Privileged Gateway Intents) — sans ca,
  on_member_join et la lecture du contenu des messages ne fonctionnent pas.

Usage: python3 welcome_bot.py
"""
import io
import os
import re
from pathlib import Path

import discord
from PIL import Image

# IDs stables plutot que noms : les noms de salons utilisent une police
# Unicode "double-struck" (Tapi​Trade-Pool) qui ne matche jamais une
# recherche en ASCII simple, meme avec .lower() — d'ou l'usage d'IDs.
WELCOME_CHANNEL_ID = 1262285118291316816  # 1・TapiTrade-Pool
TRADE_CHANNEL_ID = 1334818319177482281    # 4・Partage-de-Trades
STAFF_CHANNEL_ID = 1260936286034722959    # Tapi-TEAM
REACTIONS = ["👍", "🔥", "🚀"]

# Detecte un signe "+" colle a un chiffre (+61, +5%, +€2 188,34...) ou un mot positif de trading.
_POSITIVE_TEXT_PATTERN = re.compile(r"\+\s?\d|gain|profit|win|gagn[ée]|r[ée]ussi", re.IGNORECASE)

WELCOME_MESSAGE = (
    "# 👋 Bienvenue {mention} sur TapiTrade ! 🔑\n\n"
    "Ravi de t'avoir parmi nous ✅🎊🚀 💥 🔥.\n\n"
    "📩 Regarde tes **messages privés** (de Discord) — on vient de t'y envoyer les prochaines étapes pour débloquer tes accès !\n\n"
    "Team-TapiTrade\n"
    "You are the Key 🔑"
)

DM_ONBOARDING_MESSAGE = (
    "👋 Bienvenue dans la communauté TapiTrade !\n"
    "Pour débloquer ton accès à nos salons d'analyses et d'échanges (pendant 30 jours, "
    "le temps que tu découvres par toi-même ce qu'on fait 👀), une seule étape :\n\n"
    "📝 Réponds ici avec ces 3 infos 😗\n"
    "• Prénom 😗\n"
    "• 1ère lettre de ton nom 😗\n"
    "• Ville ou Pays 😗\n"
    "Exemple : Christian P. / Allemagne\n\n"
    "✅ Dès qu'on a tes infos, l'équipe met à jour ton pseudo et t'ouvre les accès — "
    "tu n'as rien d'autre à faire !\n"
    "À très vite,\n\n"
    "🔑 L'équipe TapiTrade — You are the Key"
)


def _load_env() -> None:
    """Charge .env en local (dev). Sur Railway, le fichier n'existe pas —
    les variables sont deja injectees dans l'environnement, on ne fait rien."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k] = v


_load_env()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)


def _image_is_greenish(image_bytes: bytes) -> bool:
    """Heuristique : vrai si le vert (gain) domine nettement le rouge (perte)
    sur l'image, en ne comptant que les pixels clairement colores dans un sens
    ou l'autre (evite le bruit du fond neutre/noir des captures de trading)."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((100, 100))  # sous-echantillonnage pour la vitesse
    pixels = img.getdata()

    green_count = 0
    red_count = 0
    for r, g, b in pixels:
        if g > r + 30 and g > b + 30 and g > 80:
            green_count += 1
        elif r > g + 30 and r > b + 30 and r > 80:
            red_count += 1

    return green_count > red_count and green_count > len(pixels) * 0.02


async def _message_looks_positive(message: discord.Message) -> bool:
    if _POSITIVE_TEXT_PATTERN.search(message.content):
        return True

    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            try:
                image_bytes = await attachment.read()
                if _image_is_greenish(image_bytes):
                    return True
            except Exception as e:
                print(f"Erreur analyse image ({attachment.filename}): {e}")

    return False


@client.event
async def on_ready() -> None:
    print(f"Connecte en tant que {client.user} — pret a accueillir les nouveaux membres.")


@client.event
async def on_member_join(member: discord.Member) -> None:
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel is None:
        print(f"ERREUR: channel {WELCOME_CHANNEL_ID} introuvable sur {member.guild.name}")
        return

    await channel.send(WELCOME_MESSAGE.format(mention=member.mention))
    print(f"Bienvenue envoyee a {member} dans #{channel.name}")

    try:
        await member.send(DM_ONBOARDING_MESSAGE)
        print(f"Message prive envoye a {member}")
    except discord.Forbidden:
        print(f"MP impossible pour {member} — DMs fermes ou bot bloque")


async def _handle_onboarding_reply(message: discord.Message) -> None:
    """Reponse a DM_ONBOARDING_MESSAGE : relaie le message recu dans
    #Tapi-TEAM, que le bot ne peut sinon jamais voir (echange prive entre le
    bot et le nouveau membre) — l'equipe change le pseudo et ouvre les acces
    manuellement, comme avant, mais avec visibilite immediate au lieu de
    dependre du membre qui recontacte quelqu'un a part."""
    member = None
    for guild in client.guilds:
        member = guild.get_member(message.author.id)
        if member:
            break
    if member is None:
        return  # DM d'un compte hors serveur (pas un onboarding a traiter)

    staff_channel = client.get_channel(STAFF_CHANNEL_ID)
    if staff_channel is None:
        print(f"ERREUR: channel staff {STAFF_CHANNEL_ID} introuvable")
        return

    await staff_channel.send(
        f"📥 Réponse d'onboarding — {member.mention} ({member})\n"
        f"> {message.content}"
    )
    print(f"Reponse d'onboarding de {member} relayee dans #Tapi-TEAM")

    try:
        await message.channel.send("✅ Merci ! L'équipe met à jour ton accès sous peu, bienvenue dans la communauté 🔑")
    except discord.Forbidden:
        pass


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        await _handle_onboarding_reply(message)
        return

    if not isinstance(message.channel, discord.TextChannel):
        return

    if message.channel.id == TRADE_CHANNEL_ID:
        # Salon special : reaction uniquement si le trade partage est gagnant.
        if await _message_looks_positive(message):
            for emoji in REACTIONS:
                await message.add_reaction(emoji)
            print(f"Reaction (trade gagnant) ajoutee sur le message de {message.author} dans #{message.channel.name}")
        return

    # Tous les autres salons : reaction automatique sur chaque message.
    for emoji in REACTIONS:
        await message.add_reaction(emoji)
    print(f"Reaction automatique ajoutee sur le message de {message.author} dans #{message.channel.name}")


def main() -> None:
    token = os.environ["DISCORD_BOT_TOKEN"]
    client.run(token)


if __name__ == "__main__":
    main()
