import pickle
import time
import datetime
import sys
import os
import re
import requests
import random
import subprocess
import getpass
import shutil
from bs4 import BeautifulSoup
from urllib.request import urlretrieve
from PIL import Image
from aip import AipOcr

# Specify your own path to store and load cookies
COOKIE_FILE = "byrcookies.pkl"
MAIN_PAGE = 'https://bt.byr.cn/'
LOGIN_PAGE = 'https://bt.byr.cn/login.php'
SESSION = requests.Session()
ACCOUNT = {}
targetspace = '/mnt/volume_sfo2_03/'

def get_account():
	''' user id
	:rtype: int
	'''
	soup = BeautifulSoup(SESSION.get(MAIN_PAGE).text, 'lxml')
	medium = soup.find('span', {'class': 'medium'})

	user = medium.find('a', href=re.compile(r'userdetails\.php'))
	ACCOUNT['userid'] = int(user.attrs['href'].split("=")[-1])
	ACCOUNT['username'] = user.text

	quotas = [
		item for item in medium.text.split() if re.search(
			r'(\d+)', item)]

	for i, e in enumerate(['bonus', 'invite', 'upload_rank',
						   'ratio', 'uploaded', 'downloaded', 'seeding', 'leeching']):
		ACCOUNT[e] = quotas[i]

	units = re.findall(r'([GMT]B)', medium.text)
	ACCOUNT['uploaded'] += ' ' + units[0] + ' ⬆'
	ACCOUNT['downloaded'] += ' ' + units[1] + ' ⬇'

	return ACCOUNT


def print_account():
	''' print account info for debugging purpose
	itype: dict / rtype: None
	'''
	for k, v in ACCOUNT.items():
		print(' {:<13} : {:<20}'.format(k, v))


def login_with_cookie():
	if not os.path.exists(COOKIE_FILE):
		return [False, None]

	SESSION.headers = {'User-Agent': 'Mozilla/5.0'}
	with open(COOKIE_FILE, 'rb') as f:
		SESSION.cookies.update(pickle.load(f))

	resp = SESSION.get(MAIN_PAGE)
	uname = ''
	if resp.url == MAIN_PAGE:
		get_account()
		print(
			">> Cookies remain valid, welcome back, " +
			ACCOUNT['username'] +
			"! 🐜 ")
		print_account()
		return [SESSION, resp]
	return [False, None]


def preview(image_file):
	img = Image.open(image_file)
	width, height = img.size
	threshold = 30

	for j in range(15, height - 15):
		for i in range(20, width - 20):
			p = img.getpixel((i, j))
			r, g, b = p
			if r > threshold or g > threshold or b > threshold:
				print(' ', end="")
			else:
				print('▓', end="")
		print()


def preconfig(image):
	img = Image.open(image)
	width, height = img.size
	threshold = 30
	for i in range(0, width):
		for j in range(0, height):
			r, g, b = img.getpixel((i, j))
			if r > threshold or g > threshold or b > threshold:
				img.putpixel((i, j), (255, 255, 255))
			else:
				img.putpixel((i, j), (0, 0, 0))
	img.save("pre_fig.jpg")


def baidu_ai_ocr(image):
	# use baidu AI ocr to parse out the result
	app_id = '11565085'
	api_key = 'dh9pPBqw1H4hQQyPrk4HHVv6'
	secret_key = '6mjlcxPsT2NRs7wETIqs3xYBjz0pdyH5'
	client = AipOcr(app_id, api_key, secret_key)

	preconfig(image)
	with open('pre_fig.jpg', 'rb') as f:
		response = client.basicGeneral(f.read(), {'language_type':'ENG'})
		return ''.join(re.findall(r'\w', response['words_result'][0]['words'])).lower()


def login():
	# First, login with cookies
	SESSION, resp = login_with_cookie()
	if SESSION:
		return [SESSION, resp]
	SESSION = requests.Session()
	SESSION.headers = {'User-Agent': 'Mozilla/5.0'}
	# html = open("login.html", 'rb').read()

	soup = BeautifulSoup(SESSION.get(LOGIN_PAGE).text, 'lxml')
	captcha_link = MAIN_PAGE + soup.findAll('img')[0].attrs['src']
	# print(">> open the following link for checking captcha:", captcha_link, sep="\n")
	urlretrieve(captcha_link, 'captcha.jpg')

	preview('captcha.jpg')
	ai_res = baidu_ai_ocr('captcha.jpg')
	prompt = input(">> baidu-ai-ocr result is {:<1}, is it correct? [y/n] ".format(ai_res))
	imagestring = ai_res if prompt.lower() == 'y' else input(">> input the correct captcha value: ")
	imagehash = captcha_link.split("=")[-1]
	
	username = input(">> byr username: ")
	password = getpass.getpass('>> byr password: ')

	params = {
		'username': username,
		'password': password,
		"imagestring": imagestring,
		'imagehash': imagehash,
	}
	# print(params)

	resp = SESSION.post('https://bt.byr.cn/takelogin.php', data=params)
	with open(COOKIE_FILE, 'wb') as f:
		print(">> login SUCCEED. saving cookies...")
		pickle.dump(SESSION.cookies, f)
	return (SESSION, resp)


# --------------------------------------------------------------------
SESSION, resp = login()
_, _, FREESPACE = [u // (2**30) for u in shutil.disk_usage(targetspace)]
# --------------------------------------------------------------------


def retrieve_torrent():
	soup = BeautifulSoup(resp.text, 'lxml')
	torrents = []
	for link in soup.findAll('a', href=re.compile("^download*")):
		down = MAIN_PAGE + link.attrs['href']
		torrent_name = down.split("=")[-1] + ".torrent"
		print('>> downloading torrent', down, '>', torrent_name)

		r = SESSION.get(down, allow_redirects=True)
		open(torrent_name, 'wb').write(r.content)
		torrents.append(torrent_name)
	return torrents


def is_downloadable(t):
	# given a torrent, return its size in unit and a random port
	cmd = 'transmission-show ' + t + " | grep Total"
	size, unit = subprocess.check_output(cmd, shell=True).split()[2:4]
	size, unit = float(size), unit.decode('utf-8')
	global FREESPACE

	if unit == 'MB' and FREESPACE >= 1:
		FREESPACE -= 1
		return True
	elif unit == 'GB' and FREESPACE >= size + 1:  # leave at least 1G for system
		FREESPACE -= size
		return True
	return False
   

def homepage_torrents():
	''' return the 5 torrents name in the homepage without actually download them
	:rtype: list of string
	'''
	soup = BeautifulSoup(resp.text, 'lxml')
	torrents = []
	for link in soup.findAll('a', href=re.compile("^download*")):
		down = MAIN_PAGE + link.attrs['href']
		tname = down.split("=")[-1] + ".torrent"
		torrents.append(tname)
	return torrents


def routine():
	global resp
	resp = SESSION.get(MAIN_PAGE)
	torrents = homepage_torrents()

	for t in torrents:
		if os.path.exists(t):
			continue
		torid = t.split('.')[0]
		r = SESSION.get(
			MAIN_PAGE +
			"download.php?id=" +
			torid,
			allow_redirects=True)
		open(t, 'wb').write(r.content)
		
		if is_downloadable(t):
			port = random.randint(20000, 30000)
			with open(os.devnull, 'w') as devnull:
				subprocess.Popen(
					['transmission-cli', '-w', targetspace, '-p', str(port), t], stdout=devnull, stderr=devnull)


def download_files():
	print(">> Terminating transmission-cli & Cleaning Downloads, torrents resume...")
	os.system("pkill -f transmission")  # terminal previous threads
	# os.system("sleep 10; rm -rf /root/Downloads/*")
	os.system("sleep 10; rm -rf " + targetspace + "/*")
	os.system("rm -f /root/.config/transmission/torrents/*")
	os.system("rm -f /root/.config/transmission/resume/*")
	os.system("rm -f *.torrent")    # removing resumes

	global FREESPACE
	_, _, FREESPACE = [u // (2**30) for u in shutil.disk_usage(targetspace)]
	print(">> Available memory: " + str(FREESPACE) + ' GB')

	# to clear redundant seeds
	SESSION.get("https://bt.byr.cn/takeflush.php?id=" + str(ACCOUNT['userid']))
	period = 30
	print(">> Seeds was flushed. Sleep for {:<2} seconds".format(period))
	time.sleep(period)

	for t in retrieve_torrent():
		try:
			if is_downloadable(t):
				port = random.randint(20000, 30000)
				print(">> downloading file from " + t)
				with open(os.devnull, 'w') as devnull:
					subprocess.Popen(
						['transmission-cli', '-w', targetspace, '-p', str(port), t], stdout=devnull, stderr=devnull)
					# os.system("transmission-cli -p " + str(port) + " " + t + " &>/dev/null&")
		except Exception as e:
			print(e)
			continue


if __name__ == '__main__':
	cter = 1000
	while True:
		period = 120
		try:
			if cter >= 24 * 3600 // period:
				cter = 0
				download_files()
			routine()
			cter += 1
			time.sleep(period)
			print(datetime.datetime.now(), 'Normal')
		except Exception as e:
			print("WHILE TRUE exception : ")
			print(e)
