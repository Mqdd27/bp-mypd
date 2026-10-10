def clean(data, strings, replace):
    for string in strings:
        data = data.replace(string, replace)
    return data

#def number(value, localization):
#    if type(value) == str:
#       return float(value.replace(',', ''))
#    import locale
#    if not localization:
#    #    localization = 'en_US.UTF-8'
#       localization = 'id_ID.utf8'
#    locale.setlocale(locale.LC_ALL, localization)
#    # if localization == 'en_US.UTF-8':
#    if localization == 'id_ID.utf8':
#       return locale.format('%.4f', value, True)
#    #locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
#    return locale.format('%.2f', value, True)


def number(value, localization):
    if type(value) == str:
        return float(value.replace(',', ''))

    import locale
    try:
        localization = localization or 'id_ID.utf8'
        locale.setlocale(locale.LC_ALL, localization)
        return locale.format('%.4f', value, True)
    except Exception as e:
        # fallback manual
        return "{:,.4f}".format(value).replace(",", "X").replace(".", ",").replace("X", ".")



def convert(data, locale=False):
   if type(data) == list:
      objects = []
      for object in data:
          if type(object) == dict:
             objects.append(convert(object, locale))
          else:
             objects.append(object)
      #if not data:
      #   data.insert(0, "")
      #   data.insert(1, "")
      #   return data
      return objects
   data = {key: number(value, locale) if type(value) == float else convert(value, locale) if type(value) == list else ["", ""] if value == False and ('_id' in key or 'uom2' in key and 'qty' not in key) else value for key,value in data.items()}
   return data


# def convert(data, locale=False):
#     log_file = '/opt/odoo16/logs/create_problem.log'

#     # HANDLE LIST
#     if type(data) == list:
#         objects = []
#         for obj in data:
#             if type(obj) == dict:
#                 objects.append(convert(obj, locale))
#             else:
#                 objects.append(obj)
#         return objects

#     result = {}

#     for key, value in data.items():
#         try:
#             # ?? LOG TYPE & VALUE
#             open(log_file, 'a+').write(
#                 f"\n[CONVERT] KEY={key} TYPE={type(value)} VALUE={value}"
#             )

#             # CASE FLOAT
#             if type(value) == float:
#                 open(log_file, 'a+').write(f" --> FLOAT DETECTED")
#                 result[key] = number(value, locale)

#             # CASE LIST
#             elif type(value) == list:
#                 open(log_file, 'a+').write(f" --> LIST DETECTED")
#                 result[key] = convert(value, locale)

#             # CASE FALSE SPECIAL
#             elif value == False and ('_id' in key or ('uom2' in key and 'qty' not in key)):
#                 open(log_file, 'a+').write(f" --> FALSE SPECIAL CASE")
#                 result[key] = ["", ""]

#             # DEFAULT
#             else:
#                 result[key] = value

#         except Exception as e:
#             # LOG ERROR DETAIL
#             open(log_file, 'a+').write(
#                 f"\n[ERROR] KEY={key} VALUE={value} ERROR={str(e)}"
#             )
#             raise

#     return result



def encode(data):
    data = {key: int(value) if isint(value) else float(value) if isfloat(value) else True if value in ['True', 'true'] else False if value in ['False', 'false'] else "" if value == 'null' else value if isinstance(value, (dict, list)) else str(value) for key,value in data.items()}
    return data

def isint(string):
    if type(string) not in [str, unicode]:
       return False
    if string.isdigit():
       return True
    else:
       return False

def isfloat(string):
    if type(string) not in [str, unicode]:
       return False
    try:
        float(string)
        return True
    except ValueError:
        return False

def sequence(data):
    if type(data) == list:
       new = []
       sequence = 1
       for object in data:
           object['sequence'] = sequence
           new.append(object)
           sequence += 1
       data = new
       return data

def json(data, cdata=True):
    from json import dumps
    '''if type(data) == list and len(data) > 3:
       objects = []
       for object in data:
           object = json(object)
           objects += [object]
       return list'''
    #data = convert(data)
    data = dumps(data)#.replace('"false"', '""').replace('false', '""')
    data = clean(data, ['"false"', 'false'], '""').replace('"", \\"', 'false, \\"')
    #data = clean(data, ['<', '>'], '')
    if cdata: data = '<![CDATA[' + data + ']]>'
    return data

def decimal(value, locale=False):
    if value == False:
       return float(value)
    return number(str(value), locale)
