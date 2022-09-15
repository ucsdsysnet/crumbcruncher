'use strict'

const parseDomain = require('parse-domain')

const urlLib = require('url')

const parseUrl = url => {
  try {
    return (new urlLib.URL(url))
  } catch (e) {
    return false
  }
}

const getHost = url => {
  const parsedUrl = parseUrl(url)
  return parsedUrl && parsedUrl.host
}

const getDomain = url => {
  const host = getHost(url)
  if (host === false) {
    return false
  }

  const domainParts = parseDomain(host)
  return domainParts && domainParts.domain
}

const guessFileExtension = url => {
  const parsedUrl = parseUrl(url)
  if (parsedUrl === false) {
    return false
  }
  const path = parsedUrl.pathname
  if (!path) {
    return false
  }

  const pathParts = path.split('.')
  const lastPathPart = pathParts[pathParts.length - 1]
  if (lastPathPart.length >= 2 && lastPathPart.length <= 4) {
    return lastPathPart.toLowerCase()
  }

  return false
}

const isHttpUrl = url => {
  try {
    return url.indexOf('http') === 0
  } catch (err) {
    return false
  }
}

module.exports = {
  getHost,
  getDomain,
  isHttpUrl,
  guessFileExtension
}
